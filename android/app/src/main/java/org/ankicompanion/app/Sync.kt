package org.ankicompanion.app

import android.content.Context
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
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPersisted(!immediate)
        if(immediate)builder.setMinimumLatency(0) else builder.setPeriodic(15*60*1000L)
        scheduler.schedule(builder.build())
    }
    fun run(context:Context):JSONObject? {
        val store=Storage(context);val config=store.connection() ?: return null
        if(!running.compareAndSet(false,true))return store.load("state.json")
        try {
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
                outbox.send(api,store.deviceId)
                if(AnkiBridge.permitted(context))api.json("/v1/snapshots","POST",JSONObject().put("device_id",store.deviceId).put("label","Android phone").put("decks",JSONArray(AnkiBridge.decks(context))).put("sync_status",AnkiBridge.capabilities(context)?.getString("sync_status") ?: "Bridge unavailable").put("collection_synced_ms",AnkiBridge.capabilities(context)?.getLong("synced_ms") ?: 0))
                val state=api.json("/v1/state");val lineup=state.getJSONObject("lineup")
                Skins(context).ensure(api,lineup.getString("skin_id"),lineup.getString("skin_version"))
                store.save("commands.json",api.json("/v1/commands/"+store.deviceId));
                Commands.notify(context)
                store.save("state.json",state);store.setSetting("sync_error","")
                AnkiBridge.configure(context,state.getJSONObject("settings"))
                try {Updates.check(context,api)}catch(e:Exception){store.setSetting("update_error",e.message ?: "Update check failed")}
                CompanionWidget.refresh(context)
                return outbox.overlay(state)
            } finally {outbox.close()}
        } catch(e:Exception) {
            store.setSetting("sync_error",e.message ?: "Offline")
            CompanionWidget.refresh(context)
            return store.load("state.json")?.let{Outbox(context).use {out->out.overlay(it)}}
        } finally {running.set(false)}
    }
}

class SyncJob:JobService() {
    override fun onStartJob(params:JobParameters):Boolean {
        Sync.executor.execute {try{Sync.run(applicationContext)}finally{jobFinished(params,false)}};return true
    }
    override fun onStopJob(params:JobParameters)=true
}

class RefreshReceiver:BroadcastReceiver() {
    override fun onReceive(context:Context,intent:Intent){Sync.schedule(context);Sync.schedule(context,true)}
}
