package org.ankicompanion.app

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.Worker
import androidx.work.WorkerParameters
import androidx.work.WorkManager
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import org.json.JSONObject

/** FCM carries only a version hint; native Anki/AnkiDroid owns the schedule. */
class CompanionFcmService:FirebaseMessagingService() {
    override fun onNewToken(token:String) {
        super.onNewToken(token)
        FcmRegistration.register(applicationContext, token)
    }

    override fun onMessageReceived(message:RemoteMessage) {
        super.onMessageReceived(message)
        if(message.data["kind"]!="anki_changed")return
        val config=Storage(this).connection() ?: return
        val changedCollection=message.data["collection_id"] ?: ""
        if(changedCollection.isNotEmpty() && changedCollection!=config.optString("collection_id","primary"))return
        FcmRegistration.wake(applicationContext,message.data["sequence"]?.toLongOrNull() ?: 0L)
    }

    override fun onDeletedMessages() {
        super.onDeletedMessages()
        FcmRegistration.wake(applicationContext,0L)
    }
}

/** One-time WorkManager wake, not a running background polling process. */
object FcmRegistration {
    fun ensure(context:Context) {
        if(Storage(context).connection()==null)return
        if(FirebaseApp.getApps(context).isEmpty()) {
            Storage(context).setSetting("fcm_status","Firebase project not configured in installed APK")
            return
        }
        FirebaseMessaging.getInstance().token
            .addOnSuccessListener { token -> register(context.applicationContext,token) }
            .addOnFailureListener { Storage(context).setSetting("fcm_status","FCM token unavailable") }
    }

    fun register(context:Context,token:String) {
        val store=Storage(context)
        val config=store.connection() ?: return
        // Registration works after pairing even when Google delivers onNewToken
        // before a Windows connection is configured.
        val fingerprint=config.optString("url")+"|"+config.optString("collection_id","primary")
        if(store.getSetting("fcm_registered_key")==fingerprint &&
            store.getSetting("fcm_registered_token")==token)return
        Sync.executor.execute {
            try {
                Api(config).json("/v1/push/register","POST",JSONObject()
                    .put("device_id",store.deviceId)
                    .put("collection_id",config.optString("collection_id","primary"))
                    .put("fcm_token",token))
                store.setSetting("fcm_registered_key",fingerprint)
                store.setSetting("fcm_registered_token",token)
                store.setSetting("fcm_status","Registered for automatic push updates")
            }catch(e:Exception){
                store.setSetting("fcm_status","Registration retry pending")
            }
        }
    }

    fun wake(context:Context,sequence:Long) {
        val store=Storage(context)
        if(store.connection()==null)return
        val previous=store.getSetting("fcm_requested_sequence","0").toLongOrNull() ?: 0L
        if(sequence>previous)store.setSetting("fcm_requested_sequence",sequence.toString())
        val builder=OneTimeWorkRequestBuilder<FcmSyncWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
        // Pre-Android 12 expedited work requires a foreground notification;
        // use a normal one-off job there rather than failing without one.
        if(android.os.Build.VERSION.SDK_INT>=31)
            builder.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
        val work=builder.build()
        // KEEP coalesces a burst of card answers; the worker checks whether a
        // higher sequence arrived while it was already synchronizing.
        WorkManager.getInstance(context).enqueueUniqueWork("companion_fcm_sync",ExistingWorkPolicy.KEEP,work)
    }
}

class FcmSyncWorker(context:Context,params:WorkerParameters):Worker(context,params) {
    override fun doWork():Result {
        val store=Storage(applicationContext)
        if(store.connection()==null)return Result.success()
        return try {
            repeat(3) {
                val before=store.getSetting("fcm_requested_sequence","0")
                if(Sync.run(applicationContext,requireFresh=true)==null)return Result.retry()
                if(store.getSetting("sync_error").isNotEmpty())return Result.retry()
                if(store.getSetting("fcm_requested_sequence","0")==before) {
                    store.setSetting("fcm_applied_sequence",before)
                    CompanionWidget.refresh(applicationContext)
                    applicationContext.sendBroadcast(
                        android.content.Intent("org.ankicompanion.app.SYNC_COMPLETE")
                            .setPackage(applicationContext.packageName))
                    return Result.success()
                }
            }
            Result.retry()
        }catch(e:Exception){Result.retry()}
    }
}