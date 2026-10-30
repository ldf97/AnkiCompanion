package org.ankicompanion.app

import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.os.Build
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicBoolean

/** Background commands surface a notification; Android forbids silent activity launches. */
object Commands {
    private val applying=AtomicBoolean(false)
    fun notify(context:Context) {
        val pending=Storage(context).load("commands.json")?.optJSONArray("commands") ?: return
        if(pending.length()==0)return
        if(Build.VERSION.SDK_INT>=33 && context.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)return
        val manager=context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("study","Study requests",NotificationManager.IMPORTANCE_DEFAULT))
        val open=PendingIntent.getActivity(context,51,Intent(context,MainActivity::class.java),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        manager.notify(51,Notification.Builder(context,"study").setSmallIcon(R.drawable.app_icon).setContentTitle("Study request received")
            .setContentText("Tap to open AnkiDroid").setContentIntent(open).setAutoCancel(true).build())
    }
    fun handle(activity:Activity,api:Api) {
        val storage=Storage(activity)
        val command=storage.load("commands.json")?.optJSONArray("commands")?.objects()?.firstOrNull() ?: return
        if(!applying.compareAndSet(false,true))return
        val id=command.getString("id");val key="command_"+id
        fun acknowledge() {
            Sync.executor.execute {
                try {api.json("/v1/commands/"+storage.deviceId+"/"+id+"/ack","POST",JSONObject())}
                catch(e:Exception){storage.setSetting("sync_error","Command applied; acknowledgement will retry")}
                finally{applying.set(false)}
            }
        }
        if(storage.getSetting(key)=="launched"){acknowledge();return}
        Sync.executor.execute {
            try {
                val state=storage.load("state.json") ?: error("Waiting for server settings")
                val settings=state.getJSONObject("settings")
                require(AnkiBridge.configure(activity,settings)){"Grant AnkiDroid Companion access to apply study requests"}
                AnkiBridge.synchronize(activity)
                val action=command.getString("action")
                require(action=="sync" || action=="study"){"Unsupported command"}
                val deck=if(action=="study") Rules.next(AnkiBridge.decks(activity),settings.getString("parent_deck_id"),settings.getString("clearance")) else null
                activity.runOnUiThread {
                    try {
                        if(activity.isFinishing)error("Study request awaits an open app")
                        if(deck!=null)AnkiBridge.open(activity,deck.getString("id"))
                        storage.setSetting(key,"launched");acknowledge()
                    }catch(e:Exception){storage.setSetting("sync_error",e.message ?: "Could not open AnkiDroid");applying.set(false)}
                }
            }catch(e:Exception){storage.setSetting("sync_error",e.message ?: "Study sync failed; request remains pending");applying.set(false)}
        }
    }
}
