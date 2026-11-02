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
    fun scan(context:Context,store:Storage,canRetract:Boolean=false) {
        val floor=System.currentTimeMillis()-370L*86400000
        val cursor=store.getSetting("history_cursor",floor.toString()).toLongOrNull() ?: floor
        val collection=store.connection()?.optString("collection_id","primary") ?: "primary"
        val items=AnkiBridge.history(context,cursor)
        val recentFloor=System.currentTimeMillis()-3600000
        val recent=mutableListOf<JSONObject>()
        var recentCursor=recentFloor
        while(true){
            val page=AnkiBridge.history(context,recentCursor);recent.addAll(page)
            if(page.size<1000)break
            recentCursor=page.last().getLong("revlog_id")+1
        }
        val known=mutableListOf<Pair<String,Long>>()
        // Avoid full-table review-history scans while answering medical cards.
        // Prioritize unsent reviews and the most recent committed answers.
        readableDatabase.rawQuery("SELECT id,payload FROM events WHERE undone=0 ORDER BY sent ASC,timestamp DESC LIMIT 1200",null).use {c->while(c.moveToNext()) {
            val item=JSONObject(c.getString(1))
            if(item.getString("collection_id")==collection)known.add(c.getString(0) to item.getLong("revlog_id"))
        }}
        val missing=mutableListOf<String>()
        // A native collection can be temporarily empty or behind during full
        // sync, profile migration, or test teardown. Such absence is NOT undo
        // evidence. Only retract when a stable completed native sync is known.
        val before=AnkiBridge.capabilities(context)
        if(canRetract && before?.getString("sync_status")=="synced") {
            for(batch in known.chunked(300)) {
                val present=AnkiBridge.history(context,0,batch.map{it.second}).map{it.getLong("revlog_id")}.toSet()
                missing.addAll(batch.filter{it.second !in present}.map{it.first})
            }
        }
        val after=AnkiBridge.capabilities(context)
        val safeToRetract=canRetract && before!=null && after!=null
            && before.getString("sync_status")=="synced" && after.getString("sync_status")=="synced"
            && before.getLong("generation")==after.getLong("generation")
        writableDatabase.beginTransaction()
        try {
            for(item in items+recent) {
                item.put("collection_id",collection);val id="$collection:${item.getLong("revlog_id")}:${item.getLong("card_id")}"
                val values=ContentValues().apply{put("id",id);put("payload",item.toString());put("timestamp",item.getLong("revlog_id"))}
                val inserted=writableDatabase.insertWithOnConflict("events",null,values,SQLiteDatabase.CONFLICT_IGNORE)
                if(inserted<0 && item.has("rating")) {
                    readableDatabase.rawQuery("SELECT payload FROM events WHERE id=?",arrayOf(id)).use{previous->
                        if(previous.moveToFirst()) {
                            val original=JSONObject(previous.getString(0))
                            if(!original.has("rating")) {
                                // Re-submit the same stable review id with richer
                                // metadata, not a second counted answer.
                                writableDatabase.execSQL("UPDATE events SET payload=?,sent=0 WHERE id=?",
                                    arrayOf(item.toString(),id))
                            }
                        }
                    }
                }
            }
            if(safeToRetract)for(id in missing)writableDatabase.execSQL("UPDATE events SET undone=1 WHERE id=?",arrayOf(id))
            writableDatabase.setTransactionSuccessful()
        } finally {writableDatabase.endTransaction()}
        if(items.size<1000)store.setSetting("backfill_pending","false")
        if(items.isNotEmpty())store.setSetting("history_cursor",(items.last().getLong("revlog_id")+1).toString())
    }
    fun send(api:Api,deviceId:String) {
        val pending=mutableListOf<Pair<String,JSONObject>>()
        readableDatabase.rawQuery("SELECT id,payload FROM events WHERE sent=0 ORDER BY timestamp DESC LIMIT 1000",null).use {c->while(c.moveToNext())pending.add(c.getString(0) to JSONObject(c.getString(1)))}
        if(pending.isNotEmpty()) {
            api.json("/v1/events","POST",JSONObject().put("device_id",deviceId).put("events",JSONArray(pending.map{it.second})))
            for(item in pending)writableDatabase.execSQL("UPDATE events SET sent=1 WHERE id=?",arrayOf(item.first))
        }
        val undone=mutableListOf<String>()
        readableDatabase.rawQuery("SELECT id FROM events WHERE undone=1 AND undo_sent=0 LIMIT 1000",null).use {c->while(c.moveToNext())undone.add(c.getString(0))}
        if(undone.isNotEmpty()) {
            api.json("/v1/events/retract","POST",JSONObject().put("ids",JSONArray(undone)).put("device_id",deviceId))
            for(id in undone)writableDatabase.execSQL("UPDATE events SET undo_sent=1 WHERE id=?",arrayOf(id))
        }
    }
    fun overlay(input:JSONObject):JSONObject {
        val state=JSONObject(input.toString());val settings=state.getJSONObject("settings");val now=System.currentTimeMillis()
        val day=Rules.day(now,settings.getString("timezone"),settings.getInt("rollover_minute"));val same=day==state.getString("date")
        val merged=mutableMapOf<String,Long>()
        if(same)state.optJSONArray("today_events")?.objects()?.forEach{merged[it.getString("id")]=it.getLong("duration_ms")}
        readableDatabase.rawQuery("SELECT id,payload,undone FROM events WHERE timestamp>=?",arrayOf((now-2*86400000L).toString())).use {c->while(c.moveToNext()) {
            val item=JSONObject(c.getString(1))
            if(Rules.day(item.getLong("revlog_id"),settings.getString("timezone"),settings.getInt("rollover_minute"))==day) {
                if(c.getInt(2)==0)merged[c.getString(0)]=item.getLong("duration_ms") else merged.remove(c.getString(0))
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
        // The overlay is a *provisional* local estimate. The server's streak
        // remains authoritative until it acknowledges the pending reviews.
        var unsent=0
        readableDatabase.rawQuery("SELECT COUNT(*) FROM events WHERE sent=0 OR (undone=1 AND undo_sent=0)",null)
            .use{cursor->if(cursor.moveToFirst())unsent=cursor.getInt(0)}
        state.put("confirmed_streak",state.optInt("streak"))
            .put("locally_pending",unsent)
            .put("completed",done).put("streak",streak)
            .put("progress",JSONObject().put("answers",merged.size).put("duration_ms",merged.values.sum()))
        state.put("local_day",day)
        return state
    }
}
