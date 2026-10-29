package org.ankicompanion.app

import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.os.Build

/** Background commands surface a notification; Android forbids silent activity launches. */
object Commands {
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
        val storage=Storage(activity);val pending=storage.load("commands.json")?.optJSONArray("commands") ?: return
        for(command in pending.objects()) {
            val id=command.getString("id");val key="command_"+id
            if(storage.getSetting(key)!="launched") {
                try {
                    when(command.getString("action")) {
                        "sync"->AnkiBridge.nativeSync(activity)
                        "study"->{
                            if(!AnkiBridge.permitted(activity))return
                            val state=storage.load("state.json") ?: return
                            val settings=state.getJSONObject("settings")
                            val deck=Rules.next(AnkiBridge.decks(activity),settings.getString("parent_deck_id"),settings.getString("clearance")) ?: return
                            AnkiBridge.open(activity,deck.getString("id"))
                        }
                    }
                    storage.setSetting(key,"launched")
                }catch(e:Exception){storage.setSetting("sync_error",e.message ?: "Could not launch AnkiDroid");return}
            }
            Sync.executor.execute {try{api.json("/v1/commands/"+storage.deviceId+"/"+id+"/ack","POST",org.json.JSONObject())}catch(e:Exception){/* retry without reopening */}}
            return
        }
    }
}
