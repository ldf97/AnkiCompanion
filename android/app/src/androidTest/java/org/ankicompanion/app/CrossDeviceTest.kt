package org.ankicompanion.app

import android.graphics.Bitmap
import android.view.Gravity
import android.widget.FrameLayout
import android.widget.TextView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.ActivityTestRule
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

@RunWith(AndroidJUnit4::class)
class CrossDeviceTest {
    @get:Rule val activityRule=ActivityTestRule(MainActivity::class.java)
    private fun signal(path:String) {
        val c=URL("http://10.0.2.2:8766/test/"+path).openConnection() as HttpURLConnection
        c.requestMethod="POST";c.doOutput=true;c.setRequestProperty("Content-Type","application/json")
        c.outputStream.use{it.write("{}".toByteArray())};c.inputStream.use{it.readBytes()};c.disconnect()
    }
    @Test fun automaticWidgetProgress() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("crossDevice")=="true")
        val activity=activityRule.activity;val instrumentation=InstrumentationRegistry.getInstrumentation();val store=Storage(activity)
        store.saveConnection(JSONObject().put("url","http://10.0.2.2:8766").put("token","emulator-fixture-token").put("allow_lan_http",true).put("collection_id","primary"))
        assertTrue("AnkiDroid permission must be granted by the harness",AnkiBridge.permitted(activity))
        instrumentation.runOnMainSync {LiveSyncService.start(activity);activity.moveTaskToBack(true)}
        signal("observer-ready")
        val evidence=File(activity.getExternalFilesDir(null),"evidence");evidence.mkdirs()
        for(count in listOf(30,50)) {
            val deadline=System.currentTimeMillis()+180000
            var state:JSONObject?=null
            while(System.currentTimeMillis()<deadline) {
                state=store.load("state.json")
                if(state?.getJSONObject("progress")?.getInt("answers")==count)break
                Thread.sleep(200)
            }
            val value=state ?: error("No automatic state received")
            assertEquals(count,value.getJSONObject("progress").getInt("answers"))
            assertEquals(count==50,value.getBoolean("completed"))
            // Render the same RemoteViews used by the home-screen widget.
            lateinit var host:FrameLayout
            instrumentation.runOnMainSync {
                host=FrameLayout(activity)
                val remote=CompanionWidget.buildViews(activity,value);val view=remote.apply(activity,host)
                val dp=activity.resources.displayMetrics.density
                host.addView(view,FrameLayout.LayoutParams((320*dp).toInt(),(160*dp).toInt(),Gravity.CENTER))
                val text=view.findViewById<TextView>(R.id.widget_status).text.toString()
                assertTrue(text.contains(if(count==30)"30/50 · 60% · 20 remaining" else "50/50 · 100% · 0 remaining"))
                activity.setContentView(host)
                val bitmap=Bitmap.createBitmap((360*dp).toInt(),(220*dp).toInt(),Bitmap.Config.ARGB_8888)
                host.measure(android.view.View.MeasureSpec.makeMeasureSpec(bitmap.width,android.view.View.MeasureSpec.EXACTLY),android.view.View.MeasureSpec.makeMeasureSpec(bitmap.height,android.view.View.MeasureSpec.EXACTLY))
                host.layout(0,0,bitmap.width,bitmap.height);host.draw(android.graphics.Canvas(bitmap))
                File(evidence,"widget-$count.png").outputStream().use{bitmap.compress(Bitmap.CompressFormat.PNG,100,it)};bitmap.recycle()
            }
            File(evidence,"state-$count.json").writeText(value.toString(2))
            signal("observed$count")
        }
    }
}
