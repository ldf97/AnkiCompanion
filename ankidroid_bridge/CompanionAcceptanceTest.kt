// SPDX-License-Identifier: GPL-3.0-or-later
package com.ichi2.anki

import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.ichi2.anki.CollectionManager.withCol
import com.ichi2.anki.previewer.CardViewerActivity
import com.ichi2.anki.settings.Prefs
import com.ichi2.anki.tests.InstrumentedTest
import com.ichi2.anki.ui.windows.reviewer.ReviewerFragment
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.net.HttpURLConnection
import java.net.URL
import android.view.View
import android.view.ViewGroup
import android.webkit.WebView
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Real AnkiDroid UI ratings and native collection sync against a disposable local server. */
@RunWith(AndroidJUnit4::class)
class CompanionAcceptanceTest : InstrumentedTest() {
    private val endpoint="http://10.0.2.2:8766"
    private fun control(path:String,body:JSONObject?=null):JSONObject {
        val c=URL(endpoint+path).openConnection() as HttpURLConnection
        c.connectTimeout=10000;c.readTimeout=60000
        if(body!=null){c.requestMethod="POST";c.doOutput=true;c.setRequestProperty("Content-Type","application/json");c.outputStream.use{it.write(body.toString().toByteArray())}}
        return c.inputStream.use{JSONObject(it.bufferedReader().readText())}.also{c.disconnect()}
    }
    private fun awaitCondition(message:String,condition:()->Boolean) {
        val deadline=System.currentTimeMillis()+180000
        while(System.currentTimeMillis()<deadline){if(condition())return;Thread.sleep(250)}
        error(message)
    }
    private fun questionRendered(scenario:ActivityScenario<CardViewerActivity>):Boolean {
        fun findWeb(view:View):WebView? {
            if(view is WebView)return view
            if(view is ViewGroup)for(i in 0 until view.childCount)findWeb(view.getChildAt(i))?.let{return it}
            return null
        }
        val ready=AtomicBoolean(false);val done=CountDownLatch(1)
        scenario.onActivity { activity ->
            val web=findWeb(activity.window.decorView)
            if(web==null)done.countDown()
            else web.evaluateJavascript("document.readyState === 'complete' && document.body.innerText.includes('Acceptance card ')") {
                ready.set(it=="true");done.countDown()
            }
        }
        return done.await(3,TimeUnit.SECONDS) && ready.get()
    }
    /**
     * Espresso's RootViewPicker intermittently cannot find the reviewer window
     * even after onResume and a fully loaded WebView on API 35 emulators.
     * Interact with the actual visible UI buttons on the Activity's main
     * thread, still exercising their real listeners and native Anki scheduler.
     */
    private fun clickVisible(scenario:ActivityScenario<CardViewerActivity>, id:Int, label:String) {
        val deadline=System.currentTimeMillis()+30000L
        var last="not found"
        while(System.currentTimeMillis()<deadline) {
            val pressed=AtomicBoolean(false)
            scenario.onActivity { activity ->
                val view=activity.findViewById<View>(id)
                last=if(view==null)"not found" else
                    "shown=${view.isShown}, enabled=${view.isEnabled}, visibility=${view.visibility}"
                if(view?.isShown==true && view.isEnabled)pressed.set(view.performClick())
            }
            if(pressed.get())return
            Thread.sleep(100)
        }
        throw AssertionError("Reviewer $label button was not ready after 30 seconds ($last)")
    }

    @Test fun desktop20Phone10Desktop20() = runBlocking {
        val auth=withCol{syncLogin("fixture","temporary-test-password","http://10.0.2.2:8767/")}
        Prefs.hkey=auth.hkey;Prefs.currentSyncUri="http://10.0.2.2:8767/";Prefs.isNewStudyScreenEnabled=true
        withCol {
            try{close(downgrade=false,forFullSync=true);fullUploadOrDownload(auth,serverUsn=null,upload=false)}finally{reopen(afterFullSync=true)}
            decks.select(1)
        }
        assertEquals(0,withCol{db.queryScalar("SELECT COUNT(*) FROM revlog WHERE ease>0")})
        control("/test/phone-ready",JSONObject())
        awaitCondition("Companion observer did not start"){control("/test/status").optBoolean("observer_ready")}
        awaitCondition("Desktop's first 20 answers were not produced"){control("/test/status").getInt("phase")==20}
        ActivityScenario.launch<CardViewerActivity>(ReviewerFragment.getIntent(testContext)).use { scenario ->
            awaitCondition("First desktop reviews were not imported automatically"){
                runBlocking{withCol{db.queryScalar("SELECT COUNT(*) FROM revlog WHERE ease>0")}}==20
            }
            repeat(10){index->
                // Read the visible card before pressing Show Answer. Button
                // presence alone does not prove the initial WebView has loaded.
                awaitCondition("Question did not finish rendering"){questionRendered(scenario)}
                clickVisible(scenario,R.id.show_answer_button,"Show Answer")
                clickVisible(scenario,R.id.easy_button,"Easy")
                awaitCondition("Review $index was not saved"){runBlocking{withCol{db.queryScalar("SELECT COUNT(*) FROM revlog WHERE ease>0")}}>=21+index}
            }
        }
        control("/test/phone-finished",JSONObject())
        // No manual sync: the production companion service/provider completes the handoff.
        awaitCondition("Desktop's final 20 reviews did not arrive automatically"){
            runBlocking{withCol{db.queryScalar("SELECT COUNT(*) FROM revlog WHERE ease>0")}}==50
        }
        val snapshot=withCol {
            fun rows(sql:String):JSONArray {
                val out=JSONArray();db.query(sql).use{c->while(c.moveToNext()){val row=JSONArray();for(i in 0 until c.columnCount)row.put(c.getLong(i));out.put(row)}};return out
            }
            JSONObject().put("reviews",rows("SELECT id,cid,ease,ivl,lastIvl FROM revlog ORDER BY id"))
                .put("cards",rows("SELECT id,queue,type,due,ivl,reps,lapses FROM cards ORDER BY id"))
        }
        assertTrue(control("/test/verify-phone",snapshot).getBoolean("matched"))
    }
}
