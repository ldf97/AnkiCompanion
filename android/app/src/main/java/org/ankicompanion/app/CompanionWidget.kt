package org.ankicompanion.app

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.app.PendingIntent
import android.content.Context
import android.content.ComponentName
import android.content.Intent
import android.widget.RemoteViews
import android.graphics.*
import android.view.View
import kotlin.math.cos

class CompanionWidget:AppWidgetProvider() {
    override fun onUpdate(context:Context,manager:AppWidgetManager,ids:IntArray){refresh(context);Sync.schedule(context);Sync.schedule(context,true)}
    override fun onAppWidgetOptionsChanged(context:Context,manager:AppWidgetManager,id:Int,options:android.os.Bundle){refresh(context)}
    companion object {
        fun refresh(context:Context) {
            val manager=AppWidgetManager.getInstance(context);val ids=manager.getAppWidgetIds(ComponentName(context,CompanionWidget::class.java))
            if(ids.isEmpty())return
            val store=Storage(context);val state=store.load("state.json")
            val views=RemoteViews(context.packageName,R.layout.widget)
            val intent=Intent(context,MainActivity::class.java).putExtra("study",true)
            views.setOnClickPendingIntent(R.id.widget_root,PendingIntent.getActivity(context,10,intent,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
            if(state!=null)try {
                val local=Outbox(context).use{it.overlay(state)};val lineup=state.getJSONObject("lineup")
                val frame=Renderer(context).draw(local,Skins(context).directory(lineup.getString("skin_id"),lineup.getString("skin_version")),false)
                val bitmap=Bitmap.createScaledBitmap(frame.image,650,277,true);views.setImageViewBitmap(R.id.widget_image,bitmap)
                // Launcher-hosted ViewFlipper animates only while visible; no timer wakes the phone.
                views.setViewVisibility(R.id.widget_warning,if(frame.warning)View.VISIBLE else View.GONE)
                if(frame.warning) {
                    val frames=intArrayOf(R.id.warning_0,R.id.warning_1,R.id.warning_2,R.id.warning_3,R.id.warning_4,R.id.warning_5,R.id.warning_6,R.id.warning_7)
                    for(i in frames.indices) {
                        val pulse=1+.125*(1-cos(i*2*Math.PI/8));val side=(58*pulse).toFloat()
                        val overlay=Bitmap.createBitmap(320,136,Bitmap.Config.ARGB_8888)
                        val c=Canvas(overlay);c.scale(320f/1100,136f/468)
                        c.drawBitmap(frame.badge,null,RectF(124-side/2,64-side/2,124+side/2,64+side/2),Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG))
                        views.setImageViewBitmap(frames[i],overlay)
                    }
                }
                val p=local.getJSONObject("progress");val goal=local.getJSONObject("policy").getInt("lesson_answers")
                val count=p.getInt("answers");val label="$count/$goal · ${minOf(100,count*100/goal)}% · ${maxOf(0,goal-count)} remaining"
                val stale=System.currentTimeMillis()-state.getLong("server_time_ms")>120000
                val update=store.load("update.json")?.optBoolean("available")==true
                views.setTextViewText(R.id.widget_status,label+if(update)" · Update available" else if(stale)" · Cached" else " · Tap to study")
                manager.updateAppWidget(ids,views);frame.image.recycle();frame.badge.recycle();bitmap.recycle()
            } catch(e:Exception){views.setTextViewText(R.id.widget_status,"Open app to finish connecting");manager.updateAppWidget(ids,views)}
            else manager.updateAppWidget(ids,views)
        }
    }
}
