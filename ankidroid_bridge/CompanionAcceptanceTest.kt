// SPDX-License-Identifier: GPL-3.0-or-later
package com.ichi2.anki

import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.click
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withId
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.ichi2.anki.CollectionManager.withCol
import com.ichi2.anki.previewer.CardViewerActivity
import com.ichi2.anki.settings.Prefs
import com.ichi2.anki.tests.InstrumentedTest
import com.ichi2.anki.tests.checkWithTimeout
import com.ichi2.anki.ui.windows.reviewer.ReviewerFragment
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.net.HttpURLConnection
import java.net.URL

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
    @Test fun desktop20Phone10Desktop20() = runBlocking {
        val auth=withCol{syncLogin("fixture","temporary-test-password","http://10.0.2.2:8767/")}
        Prefs.hkey=auth.hkey;Prefs.currentSyncUri="http://10.0.2.2:8767/";Prefs.isNewStudyScreenEnabled=true
        withCol {
            try{close(downgrade=false,forFullSync=true);fullUploadOrDownload(auth,serverUsn=null,upload=false)}finally{reopen(afterFullSync=true)}
            decks.select(1)
        }
        assertEquals(20,withCol{db.queryScalar("SELECT COUNT(*) FROM revlog WHERE ease>0")})
        control("/test/phone-ready",JSONObject())
        awaitCondition("Companion observer did not start"){control("/test/status").optBoolean("observer_ready")}
        ActivityScenario.launch<CardViewerActivity>(ReviewerFragment.getIntent(testContext)).use {
            repeat(10){index->
                onView(withId(R.id.show_answer_button)).checkWithTimeout(matches(isDisplayed()),100,30000)
                onView(withId(R.id.show_answer_button)).perform(click())
                onView(withId(R.id.easy_button)).checkWithTimeout(matches(isDisplayed()),100,30000)
                onView(withId(R.id.easy_button)).perform(click())
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
