package org.ankicompanion.app

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import java.io.IOException
import android.content.ComponentName
import android.content.BroadcastReceiver
import android.content.Intent
import android.app.job.JobInfo
import android.app.job.JobScheduler
import android.app.job.JobService
import android.app.job.JobParameters
import org.json.JSONObject
import org.json.JSONArray
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

object Sync {
    private val running=AtomicBoolean(false)
    val executor=Executors.newSingleThreadExecutor()
    fun schedule(context:Context,immediate:Boolean=false) {
        val scheduler=context.getSystemService(JobScheduler::class.java)
        val builder=JobInfo.Builder(if(immediate)201 else 200,ComponentName(context,SyncJob::class.java))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPersisted(true)
        if(immediate)builder.setMinimumLatency(0).setBackoffCriteria(10_000L,JobInfo.BACKOFF_POLICY_EXPONENTIAL)
        else builder.setPeriodic(15*60*1000L)
        scheduler.schedule(builder.build())
    }
    fun run(context:Context,requireFresh:Boolean=false):JSONObject? {
        val store=Storage(context);val config=store.connection() ?: return null
        FcmRegistration.ensure(context)
        if(!running.compareAndSet(false,true))return if(requireFresh)null else store.load("state.json")
        try {
            // A separate widget process must not read the Anki collection,
            // scan revlog, enumerate decks or launch native sync while the
            // reviewer is visible. Any ContentProvider collection lock can
            // stall the next-card/answer button. The native bridge broadcasts
            // again after the reviewer closes and completes its pending sync.
            val reviewing=try {
                AnkiBridge.capabilities(context)?.getBoolean("reviewer_active",false)==true
            } catch(_:Exception) { false }
            if(reviewing) {
                store.setSetting("bridge_status","Studying: native history and scheduling sync deferred until review closes")
                CompanionWidget.refresh(context)
                return store.load("state.json")?.let { cached ->
                    Outbox(context).use { out -> out.overlay(cached) }
                }
            }
            val api=Api(config);val outbox=Outbox(context)
            try {
                AnkiBridge.refreshNative(context)
                val capability=AnkiBridge.capabilities(context)
                if(capability!=null){
                    val generation=capability.getLong("generation").toString()
                    if(store.getSetting("native_generation")!=generation && store.getSetting("backfill_pending")!="true"){store.setSetting("history_cursor",(System.currentTimeMillis()-370L*86400000).toString());store.setSetting("backfill_pending","true");store.setSetting("native_generation",generation)}
                    outbox.scan(context,store,capability.getString("sync_status")=="synced")
                    store.setSetting("bridge_status","AnkiDroid Companion · "+capability.getString("sync_status"))
                }
                else store.setSetting("bridge_status","Stock AnkiDroid: review totals arrive through desktop after native collection sync. Live cross-device review sync is not verified.")
            }
            catch(e:Exception){store.setSetting("bridge_status","AnkiDroid review-history bridge unavailable; desktop reports phone reviews after collection sync")}
            try {
                outbox.send(api,store.deviceId,store)
                val collectionId=config.optString("collection_id","primary")
                fun reportNative(applied:Long,ticket:String="") {
                    if(!AnkiBridge.permitted(context))return
                    val capability=AnkiBridge.capabilities(context)
                    api.json("/v1/snapshots","POST",JSONObject()
                        .put("device_id",store.deviceId).put("collection_id",collectionId)
                        .put("applied_revision",applied).put("native_generation",capability?.getLong("generation") ?: 0L)
                        .put("native_upload_ticket",ticket)
                        .put("label","Android phone")
                        .put("decks",JSONArray(AnkiBridge.decks(context)))
                        .put("sync_status",capability?.getString("sync_status") ?: "Bridge unavailable")
                        .put("collection_synced_ms",capability?.getLong("synced_ms") ?: 0L))
                }
                val applied=store.getSetting("native_applied_revision","0").toLongOrNull() ?: 0L
                reportNative(applied)
                val state=api.json("/v1/state?device_id="+java.net.URLEncoder.encode(store.deviceId,"UTF-8")
                    +"&collection_id="+java.net.URLEncoder.encode(collectionId,"UTF-8"))
                val lineup=state.getJSONObject("lineup")
                Skins(context).ensure(api,lineup.getString("skin_id"),lineup.getString("skin_version"))
                store.save("commands.json",api.json("/v1/commands/"+store.deviceId));
                Commands.notify(context)
                store.save("state.json",state);store.setSetting("sync_error","")
                AnkiBridge.configure(context,state.getJSONObject("settings"))
                val sync=state.optJSONObject("native_sync")
                val ticket=sync?.optString("outgoing_ticket","")?.ifEmpty {store.getSetting("native_upload_ticket")} ?: store.getSetting("native_upload_ticket")
                if(ticket.isNotEmpty())store.setSetting("native_upload_ticket",ticket)
                val remotePending=sync?.optBoolean("pending")==true
                val nativeCollision=sync?.optBoolean("conflicted")==true
                if(nativeCollision) {
                    store.setSetting("bridge_status","Native review-ID collision: scheduling sync paused; study attempts saved")
                    store.setSetting("native_retry_pending","false")
                } else if(ticket.isNotEmpty() || remotePending) {
                    try {
                        // A successful native Anki sync BEFORE publishing its
                        // matching server ticket proves the collection upload
                        // occurred. A stale prior synced timestamp is insufficient.
                        // Runs only on Sync.executor, never the card reviewer UI.
                        AnkiBridge.synchronize(context)
                        val version=if(remotePending)sync!!.getLong("revision") else applied
                        reportNative(version,ticket)
                        store.setSetting("native_retry_pending","false")
                        if(ticket.isNotEmpty())store.setSetting("native_upload_ticket","")
                        store.setSetting("native_applied_revision",version.toString())
                    } catch(e:Exception){
                        store.setSetting("bridge_status","Scheduling sync pending: "+(e.message ?: "Native sync unavailable"))
                        val reason=e.message ?: ""
                        store.setSetting("native_retry_pending",if(reason.startsWith("Initial/full") ||
                            reason.startsWith("Sign in"))"false" else "true")
                    }
                }
                try {Updates.check(context)}catch(e:Exception){store.setSetting("update_error",e.message ?: "Update check failed")}
                try {Updates.checkAnkiDroid(context)}catch(e:Exception){store.setSetting("ankidroid_update_error",e.message ?: "Update check failed")}
                // The first state was fetched BEFORE native synchronization.
                // Never cache that stale pending revision as the final result.
                val finalState=if(ticket.isNotEmpty() || remotePending) {
                    api.json("/v1/state?device_id="+java.net.URLEncoder.encode(store.deviceId,"UTF-8")
                        +"&collection_id="+java.net.URLEncoder.encode(collectionId,"UTF-8"))
                } else state
                store.save("state.json",finalState)
                CompanionWidget.refresh(context)
                return outbox.overlay(finalState)
            } finally {outbox.close()}
        } catch(e:Exception) {
            store.setSetting("sync_error",e.message ?: "Offline")
            CompanionWidget.refresh(context)
            return store.load("state.json")?.let{Outbox(context).use {out->out.overlay(it)}}
        } finally {running.set(false)}
    }
    /** A disconnected learner can always study the installed Anki collection.
     * Keep pending answers/undo events durable, and retry on network return.
     * This is local-first study, NOT a claim that another device is current.
     */
    private fun offlineStudy(context:Context,store:Storage):JSONObject {
        val cached=store.load("state.json")?.optJSONObject("settings")
            ?: error("Connect once to choose your deck before offline studying")
        store.setSetting("study_handoff_mode","offline")
        store.setSetting("bridge_status","Offline study: local Anki scheduling; synchronization queued")
        schedule(context,true)
        return cached
    }

    /** Device-handoff barrier: verify fresh scheduling when connected.
     * When genuinely offline, permit local studying instead of blocking habit.
     * Never pretend the local queue is synchronized with another device.
     */
    fun prepareStudy(context:Context):JSONObject {
        val store=Storage(context)
        val connectivity=context.getSystemService(ConnectivityManager::class.java)
        val available=connectivity.activeNetwork?.let {network->
            connectivity.getNetworkCapabilities(network)?.hasCapability(
                NetworkCapabilities.NET_CAPABILITY_INTERNET)==true
        } ?: false
        if(!available)return offlineStudy(context,store)
        val config=store.connection() ?: return offlineStudy(context,store)
        run(context)
        if(store.getSetting("sync_error").isNotBlank())return offlineStudy(context,store)
        val api=Api(config)
        val collection=config.optString("collection_id","primary")
        val device=java.net.URLEncoder.encode(store.deviceId,"UTF-8")
        val collectionEncoded=java.net.URLEncoder.encode(collection,"UTF-8")
        val url="/v1/state?device_id=$device&collection_id=$collectionEncoded"
        // A long offline queue can exceed one upload request; drain it before
        // permitting another device to create scheduling conflicts.
        Outbox(context).use { out ->
            repeat(10) {
                if(!out.hasUnsent())return@repeat
                out.send(api,store.deviceId,store)
            }
            require(!out.hasUnsent()){"Pending reviews are still uploading; retry study handoff"}
        }
        val before=try {api.json(url)}catch(e:IOException){return offlineStudy(context,store)}
        if(before.getJSONObject("native_sync").optBoolean("conflicted")) {
            // Keep local-first studying available; DO NOT certify a remote
            // schedule containing two cards with one native Anki revlog ID.
            store.setSetting("study_handoff_mode","local_unsynced")
            store.setSetting("bridge_status","Native review-ID collision; studying locally, cross-device scheduling paused")
            return before.getJSONObject("settings")
        }
        AnkiBridge.configure(context,before.getJSONObject("settings"))
        // Even with no companion revision pending, an external AnkiWeb update
        // may exist. Native synchronization is mandatory for ONLINE handoff.
        try{AnkiBridge.synchronize(context)}catch(e:IllegalStateException){
            if(e.message?.startsWith("Offline")==true)return offlineStudy(context,store)
            throw e // full-sync conflicts require Anki to choose a direction
        }
        val capability=AnkiBridge.capabilities(context)
            ?: error("AnkiDroid Companion permission/sync unavailable")
        require(capability.getString("sync_status")=="synced"){
            "Native scheduling synchronization incomplete; study handoff deferred"
        }
        val sync=before.getJSONObject("native_sync")
        val revision=sync.optLong("revision",0L)
        val ticket=sync.optString("outgoing_ticket","").ifEmpty {store.getSetting("native_upload_ticket")}
        api.json("/v1/snapshots","POST",JSONObject()
            .put("device_id",store.deviceId).put("collection_id",collection)
            .put("applied_revision",revision)
            .put("native_generation",capability.getLong("generation"))
            .put("native_upload_ticket",ticket).put("label","Android phone")
            .put("decks",JSONArray(AnkiBridge.decks(context)))
            .put("sync_status","synced")
            .put("collection_synced_ms",capability.getLong("synced_ms")))
        val fresh=api.json(url)
        val newest=fresh.getJSONObject("native_sync")
        require(!newest.optBoolean("pending") && newest.optString("outgoing_ticket","").isEmpty()){
            "Another device changed the collection during handoff; synchronize again before studying"
        }
        store.setSetting("native_applied_revision",newest.optLong("applied_revision",revision).toString())
        store.setSetting("native_upload_ticket","")
        store.setSetting("native_retry_pending","false")
        store.setSetting("study_handoff_mode","verified")
        store.save("state.json",fresh)
        CompanionWidget.refresh(context)
        return fresh.getJSONObject("settings")
    }

}

class SyncJob:JobService() {
    override fun onStartJob(params:JobParameters):Boolean {
        Sync.executor.execute {
            try{Sync.run(applicationContext)}finally{
                val store=Storage(applicationContext)
                val retry=params.jobId!=200 && (store.getSetting("sync_error").isNotBlank() ||
                    store.getSetting("native_retry_pending")=="true")
                jobFinished(params,retry)
            }
        };return true
    }
    override fun onStopJob(params:JobParameters)=true
}

class RefreshReceiver:BroadcastReceiver() {
    override fun onReceive(context:Context,intent:Intent){
        // Rebind launcher widget PendingIntents immediately after an APK update;
        // do not leave the old, sync-blocking widget tap active until next poll.
        CompanionWidget.refresh(context)
        Sync.schedule(context)
        Sync.schedule(context,true)
    }
}