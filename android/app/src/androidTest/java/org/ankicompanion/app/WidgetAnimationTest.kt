package org.ankicompanion.app

import android.view.View
import android.widget.FrameLayout
import android.widget.RemoteViews
import android.widget.ViewFlipper
import android.widget.TextView
import android.graphics.Bitmap
import org.json.JSONObject
import org.json.JSONArray
import java.io.File
import java.time.LocalDate
import java.time.ZoneOffset
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.ActivityTestRule
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Real Android RemoteViews inflation/animation; not a launcher or AnkiDroid test. */
@RunWith(AndroidJUnit4::class)
class WidgetAnimationTest {
    @get:Rule val activityRule=ActivityTestRule(MainActivity::class.java)
    @Test fun warningFramesActuallyAdvanceWhenAttached() {
        val activity=activityRule.activity;val instrumentation=InstrumentationRegistry.getInstrumentation()
        val root=Skins(activity).directory("study_companion","1.0.0");root.mkdirs()
        fun copyAsset(path:String,dest:File) {
            val children=instrumentation.context.assets.list(path)!!
            if(children.isEmpty()){dest.parentFile!!.mkdirs();instrumentation.context.assets.open(path).use{input->dest.outputStream().use{input.copyTo(it)}}}
            else {dest.mkdirs();for(child in children)copyAsset("$path/$child",File(dest,child))}
        }
        copyAsset("widget",root)
        val skin=JSONObject(File(root,"skin.json").readText());val day=LocalDate.now(ZoneOffset.UTC).toString()
        val settings=JSONObject().put("timezone","UTC").put("rollover_minute",0).put("lesson_answers",50).put("lesson_ms",0)
        val state=JSONObject().put("settings",settings).put("policy",settings).put("date",day).put("seed","emulator-fixture")
            .put("lineup",Rules.lineup(day,skin,"emulator-fixture")).put("completed",false).put("streak",72).put("server_time_ms",System.currentTimeMillis())
            .put("today_events",JSONArray((1..30).map{JSONObject().put("id","fixture:$it").put("duration_ms",1000)}))
        val evidence=File(activity.getExternalFilesDir(null),"evidence");evidence.mkdirs()
        fun screenshot(name:String){instrumentation.uiAutomation.takeScreenshot().let{image->File(evidence,name).outputStream().use{image.compress(Bitmap.CompressFormat.PNG,100,it)};image.recycle()}}
        lateinit var flipper:ViewFlipper
        var first=0
        instrumentation.runOnMainSync {
            val parent=FrameLayout(activity)
            val remote=CompanionWidget.buildViews(activity,state)
            val view=remote.apply(activity,parent);parent.addView(view,FrameLayout.LayoutParams((320*activity.resources.displayMetrics.density).toInt(),(160*activity.resources.displayMetrics.density).toInt(),android.view.Gravity.CENTER))
            activity.setContentView(parent)
            flipper=view.findViewById(R.id.widget_warning)
            assertEquals(8,flipper.childCount)
            assertTrue(view.findViewById<TextView>(R.id.widget_status).text.contains("30/50 · 60% · 20 remaining"))
        }
        instrumentation.waitForIdleSync()
        Thread.sleep(800) // Allow the first actual surface frame before recording evidence.
        instrumentation.runOnMainSync {assertTrue(flipper.isFlipping);first=flipper.displayedChild}
        // Wait on the instrumentation thread, leaving Android's main looper free.
        screenshot("warning-before.png")
        Thread.sleep(350)
        instrumentation.runOnMainSync {assertNotEquals(first,flipper.displayedChild)}
        screenshot("warning-after.png")
    }
}
