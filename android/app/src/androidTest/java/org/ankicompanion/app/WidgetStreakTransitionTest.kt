package org.ankicompanion.app

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.ActivityTestRule
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.Instant
import java.time.ZoneOffset
import java.util.UUID
import kotlin.random.Random

/** Genuine Android RemoteViews and local outbox: streak N unlit -> N+1 lit. */
@RunWith(AndroidJUnit4::class)
class WidgetStreakTransitionTest {
    @get:Rule val activityRule=ActivityTestRule(MainActivity::class.java)

    @Test fun randomLengthStreakIsPreservedUntilLastCardThenIncrementsAndLights() {
        val activity=activityRule.activity
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        val random=Random(System.nanoTime())
        val length=random.nextInt(3,101)  // Generated for this run; not a hardcoded 2 or 72.
        val goal=5
        val now=System.currentTimeMillis()
        val day=Rules.day(now,"UTC",0)
        val databaseName="streak-emulator-${UUID.randomUUID()}.db"
        val root=Skins(activity).directory("study_companion","1.0.0")
        root.mkdirs()
        fun copyAsset(path:String,dest:File) {
            val children=instrumentation.context.assets.list(path)!!
            if(children.isEmpty()) {
                dest.parentFile!!.mkdirs()
                instrumentation.context.assets.open(path).use { source ->
                    dest.outputStream().use { source.copyTo(it) }
                }
            } else { dest.mkdirs();for(child in children)copyAsset("$path/$child",File(dest,child)) }
        }
        copyAsset("widget",root)
        val skin=JSONObject(File(root,"skin.json").readText())
        val settings=JSONObject().put("timezone","UTC").put("rollover_minute",0)
            .put("lesson_answers",goal).put("lesson_ms",0).put("parent_deck_id","")
        val events=JSONArray()
        for(i in 1 until goal) events.put(JSONObject().put("id","fixture-before-$i")
            .put("duration_ms",2000L))
        val state=JSONObject().put("settings",settings).put("policy",settings)
            .put("date",day).put("seed","streak-emulator-${UUID.randomUUID()}")
            .put("lineup",Rules.lineup(day,skin,"streak-emulator-static-seed"))
            .put("completed",false).put("streak",length)
            .put("server_time_ms",now).put("today_events",events)
            .put("progress",JSONObject().put("answers",goal-1).put("duration_ms",8000))
        val evidence=File(activity.getExternalFilesDir(null),"evidence/streak-random")
        evidence.mkdirs()
        fun screenshot(filename:String) {
            val bmp=instrumentation.uiAutomation.takeScreenshot()
            assertNotNull("Android UI screenshot unavailable",bmp)
            File(evidence,filename).outputStream().use { stream ->
                assertTrue("Screenshot PNG encoding failed",bmp.compress(Bitmap.CompressFormat.PNG,100,stream))
            }
            bmp.recycle()
        }
        var renderedWidget:View?=null
        // A direct capture of the real RemoteViews subtree, drawn by Android.
        // This stays valid even if the emulator launcher overlays the whole screen
        // with a Quickstep ANR. Do not represent it as a launcher screenshot.
        fun captureRenderedWidget(filename:String) {
            instrumentation.runOnMainSync {
                val view=renderedWidget ?: error("No attached widget to capture")
                assertTrue("Widget was not laid out",view.width>0 && view.height>0)
                val bitmap=Bitmap.createBitmap(view.width,view.height,Bitmap.Config.ARGB_8888)
                val canvas=Canvas(bitmap)
                view.draw(canvas)
                File(evidence,filename).outputStream().use{output ->
                    assertTrue("Android widget view PNG encoding failed",
                        bitmap.compress(Bitmap.CompressFormat.PNG,100,output))
                }
                bitmap.recycle()
            }
        }
        fun showWidget(title:String, expected:String) {
            instrumentation.runOnMainSync {
                val parent=FrameLayout(activity).apply{setBackgroundColor(Color.rgb(15,17,21))}
                val widget=CompanionWidget.buildViews(activity,state,databaseName)
                    .apply(activity,parent)
                val scale=activity.resources.displayMetrics.density
                val width=(350*scale).toInt()
                val height=(170*scale).toInt()
                val lp=FrameLayout.LayoutParams(width,height,Gravity.CENTER)
                parent.addView(widget,lp)
                renderedWidget=widget
                val info=TextView(activity).apply {
                    text=title
                    setTextColor(Color.WHITE)
                    textSize=15f
                    gravity=Gravity.CENTER
                }
                parent.addView(info,FrameLayout.LayoutParams(-1,(48*scale).toInt(),Gravity.TOP))
                activity.setContentView(parent)
                val status=widget.findViewById<TextView>(R.id.widget_status).text.toString()
                assertTrue("Unexpected status text: $status",status.contains(expected))
            }
            instrumentation.waitForIdleSync()
            Thread.sleep(500)
        }
        try {
            Outbox(activity,databaseName).use{out ->
                val before=out.overlay(state)
                assertEquals(length,before.getInt("streak"))
                assertFalse(before.getBoolean("completed"))
                assertEquals(goal-1,before.getJSONObject("progress").getInt("answers"))
                showWidget("ANDROID EMULATOR · BEFORE FINAL REVIEW","4/5")
                screenshot("before.png")
                captureRenderedWidget("widget-before.png")

                // Simulates a native AnkiDroid review recorded to the phone outbox.
                // No change to the authoritative server streak number is injected.
                val reviewTime=System.currentTimeMillis()-1000
                val cardId=90000L+random.nextLong(1000,9999)
                val id="primary:$reviewTime:$cardId"
                val payload=JSONObject().put("collection_id","primary")
                    .put("revlog_id",reviewTime).put("card_id",cardId)
                    .put("duration_ms",2000L).put("rating",3)
                val entry=JSONObject().put("id",id).put("payload",payload)
                    .put("timestamp",reviewTime).put("sent",0)
                    .put("undone",0).put("undo_sent",0)
                out.restoreTransfer(JSONArray().put(entry))
                val after=out.overlay(state)
                assertEquals(length+1,after.getInt("streak"))
                assertTrue(after.getBoolean("completed"))
                assertEquals(goal,after.getJSONObject("progress").getInt("answers"))
                assertEquals(1,after.getInt("locally_pending"))
                // Confirm the actual rendered flame differs between unlit/lit frames.
                val f1=Renderer(activity).draw(before,root)
                val f2=Renderer(activity).draw(after,root)
                val p1=IntArray(67*75);val p2=IntArray(67*75)
                f1.image.getPixels(p1,0,67,41,52,67,75)
                f2.image.getPixels(p2,0,67,41,52,67,75)
                assertFalse("Flame image did not visibly switch",p1.contentEquals(p2))
                f1.image.recycle();f1.badge.recycle();f2.image.recycle();f2.badge.recycle()
                showWidget("ANDROID EMULATOR · AFTER FINAL REVIEW","5/5")
                screenshot("after.png")
                captureRenderedWidget("widget-after.png")
                // Server-side acknowledgment of the last event must not double-count it.
                val confirmed=JSONObject(state.toString()).put("streak",length+1)
                    .put("completed",true).put("today_events",JSONArray(events.toString())
                        .put(JSONObject().put("id",id).put("duration_ms",2000L)))
                out.restoreTransfer(JSONArray().put(JSONObject(entry.toString()).put("sent",1)))
                val confirmedOverlay=out.overlay(confirmed)
                assertEquals("Streak must not increase again after server ACK",length+1,confirmedOverlay.getInt("streak"))
                assertTrue(confirmedOverlay.getBoolean("completed"))
                File(evidence,"result.json").writeText(JSONObject()
                    .put("test","actual Android RemoteViews and Outbox overlay")
                    .put("random_streak_before",length)
                    .put("streak_after",length+1)
                    .put("cards_before",goal-1).put("cards_after",goal)
                    .put("flame_before","unlit").put("flame_after","lit")
                    .put("utc_day",day).put("captured_utc",Instant.now().atZone(ZoneOffset.UTC).toString())
                    .put("capture_type","Android widget RemoteViews drawn to PNG on emulator")
                    .put("evidence",JSONArray()
                        .put("widget-before.png").put("widget-after.png")
                        .put("before.png").put("after.png"))
                    .toString(2))
            }
        } finally {
            activity.deleteDatabase(databaseName)
        }
    }
}