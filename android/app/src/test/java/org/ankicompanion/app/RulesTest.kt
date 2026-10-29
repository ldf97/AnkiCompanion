package org.ankicompanion.app

import org.junit.Assert.*
import org.junit.Test
import org.json.JSONObject
import java.time.Instant

class RulesTest {
    private fun fixture():JSONObject = JSONObject(javaClass.classLoader!!.getResourceAsStream("rules-vectors.json")!!.bufferedReader().readText())
    @Test fun pythonAndKotlinProduceSameDailyLineups() {
        val data=fixture();val skin=data.getJSONObject("skin")
        for(vector in data.getJSONArray("vectors").objects()) {
            val actual=Rules.lineup(vector.getString("date"),skin,data.getString("seed"));val expected=vector.getJSONObject("lineup")
            for(key in listOf("date","skin_id","skin_version"))assertEquals(expected.getString(key),actual.getString(key))
            val records=expected.getJSONObject("records")
            records.keys().forEach {slot->for(key in listOf("portrait","quote","episode","background"))
                assertEquals(records.getJSONObject(slot).get(key),actual.getJSONObject("records").getJSONObject(slot).get(key))}
        }
    }
    @Test fun timeBoundariesAndCompletionOverride() {
        val skin=fixture().getJSONObject("skin")
        for((minute,id) in listOf(0 to "friendly",599 to "friendly",600 to "pensive",899 to "pensive",900 to "threatening",1079 to "threatening",1080 to "evening",1259 to "evening",1260 to "rumbling",1439 to "rumbling"))assertEquals(id,Rules.slot(skin,minute,false).getString("id"))
        assertEquals("freedom",Rules.slot(skin,1300,true).getString("id"))
        assertEquals(0f,Rules.tint(skin,600,false));assertEquals(.45f,Rules.tint(skin,1259,false),.0001f);assertEquals(0f,Rules.tint(skin,1260,false));assertEquals(0f,Rules.tint(skin,1259,true))
    }
    @Test fun daylightSavingRolloverUsesWallClock() {
        assertEquals("2026-10-31",Rules.day(Instant.parse("2026-11-01T06:30:00Z").toEpochMilli(),"America/New_York",240))
        assertEquals("2026-11-01",Rules.day(Instant.parse("2026-11-01T09:00:00Z").toEpochMilli(),"America/New_York",240))
    }
    @Test fun clearanceUsesNewCardsAndNaturalSubdeckOrder() {
        val decks=listOf(JSONObject("{\"id\":\"1\",\"name\":\"M2\",\"new\":5,\"review\":1,\"learning\":0}"),
            JSONObject("{\"id\":\"2\",\"name\":\"M2::Deck 10\",\"new\":3,\"review\":0,\"learning\":0}"),
            JSONObject("{\"id\":\"3\",\"name\":\"M2::Deck 2\",\"new\":2,\"review\":0,\"learning\":0}"),
            JSONObject("{\"id\":\"4\",\"name\":\"M2::Deck 1\",\"new\":0,\"review\":1,\"learning\":0}"))
        assertEquals("3",Rules.next(decks,"1","new_only")!!.getString("id"));assertEquals("4",Rules.next(decks,"1","new_and_reviews")!!.getString("id"))
        assertNull(Rules.next(decks,"missing","new_only"))
    }
}
