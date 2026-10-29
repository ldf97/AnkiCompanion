package org.ankicompanion.app

import android.content.Context
import android.database.sqlite.SQLiteOpenHelper
import android.database.sqlite.SQLiteDatabase
import android.content.ContentValues
import org.json.JSONObject
import org.json.JSONArray

class Outbox(context:Context):SQLiteOpenHelper(context,"reviews.db",null,1) {
    override fun onCreate(db:SQLiteDatabase) {
        db.execSQL("CREATE TABLE events(id TEXT PRIMARY KEY,payload TEXT NOT NULL,timestamp INTEGER NOT NULL,sent INTEGER NOT NULL DEFAULT 0,undone INTEGER NOT NULL DEFAULT 0,undo_sent INTEGER NOT NULL DEFAULT 0)")
    }
    override fun onUpgrade(db:SQLiteDatabase,old:Int,new:Int) {}
    fun scan(context:Context,store:Storage) {
        val floor=System.currentTimeMillis()-370L*86400000
        val cursor=store.getSetting("history_cursor",floor.toString()).toLong()
        val collection=store.connection()?.optString("collection_id","primary") ?: "primary"
        val items=AnkiBridge.history(context,cursor)
        val recentFloor=System.currentTimeMillis()-3600000
        val recent=AnkiBridge.history(context,recentFloor)
        writableDatabase.beginTransaction()
        try {
            for(item in items+recent) {
                item.put("collection_id",collection);val id="$collection:${item.getLong("revlog_id")}:${item.getLong("card_id")}"
                val values=ContentValues().apply{put("id",id);put("payload",item.toString());put("timestamp",item.getLong("revlog_id"))}
                writableDatabase.insertWithOnConflict("events",null,values,SQLiteDatabase.CONFLICT_IGNORE)
            }
            if(recent.size<1000) {
                val present=recent.map{"$collection:${it.getLong("revlog_id")}:${it.getLong("card_id")}"}.toSet()
                readableDatabase.rawQuery("SELECT id,payload FROM events WHERE timestamp>=? AND undone=0",arrayOf(recentFloor.toString())).use {c->
                    while(c.moveToNext())if(JSONObject(c.getString(1)).getString("collection_id")==collection && c.getString(0) !in present)
                        writableDatabase.execSQL("UPDATE events SET undone=1 WHERE id=?",arrayOf(c.getString(0)))
                }
            }
            writableDatabase.setTransactionSuccessful()
        } finally {writableDatabase.endTransaction()}
        if(items.isNotEmpty())store.setSetting("history_cursor",(items.last().getLong("revlog_id")+1).toString())
    }
    fun send(api:Api,deviceId:String) {
        val pending=mutableListOf<Pair<String,JSONObject>>()
        readableDatabase.rawQuery("SELECT id,payload FROM events WHERE sent=0 LIMIT 1000",null).use {c->while(c.moveToNext())pending.add(c.getString(0) to JSONObject(c.getString(1)))}
        if(pending.isNotEmpty()) {
            api.json("/v1/events","POST",JSONObject().put("device_id",deviceId).put("events",JSONArray(pending.map{it.second})))
            for(item in pending)writableDatabase.execSQL("UPDATE events SET sent=1 WHERE id=?",arrayOf(item.first))
        }
        val undone=mutableListOf<String>()
        readableDatabase.rawQuery("SELECT id FROM events WHERE undone=1 AND undo_sent=0 LIMIT 1000",null).use {c->while(c.moveToNext())undone.add(c.getString(0))}
        if(undone.isNotEmpty()) {
            api.json("/v1/events/retract","POST",JSONObject().put("ids",JSONArray(undone)))
            for(id in undone)writableDatabase.execSQL("UPDATE events SET undo_sent=1 WHERE id=?",arrayOf(id))
        }
    }
    fun overlay(input:JSONObject):JSONObject {
        val state=JSONObject(input.toString());val settings=state.getJSONObject("settings");val now=System.currentTimeMillis()
        val day=Rules.day(now,settings.getString("timezone"),settings.getInt("rollover_minute"));val same=day==state.getString("date")
        val merged=mutableMapOf<String,Int>()
        if(same)state.optJSONArray("today_events")?.objects()?.forEach{merged[it.getString("id")]=it.getInt("duration_ms")}
        readableDatabase.rawQuery("SELECT id,payload,undone FROM events WHERE timestamp>=?",arrayOf((now-2*86400000L).toString())).use {c->while(c.moveToNext()) {
            val item=JSONObject(c.getString(1))
            if(Rules.day(item.getLong("revlog_id"),settings.getString("timezone"),settings.getInt("rollover_minute"))==day) {
                if(c.getInt(2)==0)merged[c.getString(0)]=item.getInt("duration_ms") else merged.remove(c.getString(0))
            }
        }}
        val policy=if(same)state.getJSONObject("policy") else settings
        val done=merged.size>=policy.getInt("lesson_answers") && merged.values.sum()>=policy.getInt("lesson_ms")
        val previous=state.getBoolean("completed");var streak=state.getInt("streak")
        if(same){if(done && !previous)streak++;if(!done && previous)streak=(streak-1).coerceAtLeast(0)}
        else {
            val yesterday=java.time.LocalDate.parse(day).minusDays(1).toString()
            streak=if(state.getString("date")==yesterday && previous)streak else 0
            if(done)streak++
        }
        state.put("completed",done).put("streak",streak).put("progress",JSONObject().put("answers",merged.size).put("duration_ms",merged.values.sum()))
        state.put("local_day",day)
        return state
    }
}
