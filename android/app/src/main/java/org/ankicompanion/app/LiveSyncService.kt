package org.ankicompanion.app

import android.app.*
import android.content.*
import android.os.*

/** Explicit, user-started study session; Android 15 limits dataSync to six hours. */
class LiveSyncService:Service() {
    private val handler=Handler(Looper.getMainLooper())
    private var active=false
    private val tick=object:Runnable {override fun run(){
        if(!active)return
        Sync.executor.execute {
            try {Sync.run(applicationContext)}finally{if(active)handler.postDelayed(this,5000)}
        }
    }}
    override fun onBind(intent:Intent?)=null
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int {
        if(intent?.action=="stop"){stopSelf();return START_NOT_STICKY}
        val manager=getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("live","Live study progress",NotificationManager.IMPORTANCE_LOW))
        val stop=PendingIntent.getService(this,41,Intent(this,LiveSyncService::class.java).setAction("stop"),PendingIntent.FLAG_IMMUTABLE)
        val open=PendingIntent.getActivity(this,42,Intent(this,MainActivity::class.java),PendingIntent.FLAG_IMMUTABLE)
        startForeground(41,Notification.Builder(this,"live").setSmallIcon(R.drawable.app_icon)
            .setContentTitle("Live companion updates").setContentText("Study session · Android may pause after 6 hours")
            .setContentIntent(open).setOngoing(true).addAction(Notification.Action.Builder(null,"Stop",stop).build()).build())
        if(!active){active=true;handler.post(tick)}
        return START_NOT_STICKY
    }
    override fun onTimeout(startId:Int,fgsType:Int){stopSelf()}
    override fun onDestroy(){active=false;handler.removeCallbacksAndMessages(null);super.onDestroy()}
    companion object {fun start(context:Context){context.startForegroundService(Intent(context,LiveSyncService::class.java))}}
}
