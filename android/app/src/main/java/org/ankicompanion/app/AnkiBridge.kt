package org.ankicompanion.app

import android.content.Context
import android.content.Intent
import android.content.ContentValues
import android.net.Uri
import android.content.pm.PackageManager
import org.json.JSONObject
import org.json.JSONArray

object AnkiBridge {
    const val PERMISSION="com.ichi2.anki.permission.READ_WRITE_DATABASE"
    private const val ROOT="content://com.ichi2.anki.flashcards"
    fun permitted(context:Context)=context.checkSelfPermission(PERMISSION)==PackageManager.PERMISSION_GRANTED
    fun decks(context:Context):List<JSONObject> {
        if(!permitted(context))return emptyList()
        val result=mutableListOf<JSONObject>()
        context.contentResolver.query(Uri.parse("$ROOT/decks"),arrayOf("deck_id","deck_name","deck_count"),null,null,null)?.use {cursor ->
            while(cursor.moveToNext()) {
                val counts=JSONArray(cursor.getString(cursor.getColumnIndexOrThrow("deck_count")))
                result.add(JSONObject().put("id",cursor.getLong(cursor.getColumnIndexOrThrow("deck_id")).toString())
                    .put("name",cursor.getString(cursor.getColumnIndexOrThrow("deck_name"))).put("learning",counts.getInt(0)).put("review",counts.getInt(1)).put("new",counts.getInt(2)))
            }
        };return result
    }
    fun experimental(context:Context)=Storage(context).getSetting("experimental_bridge","false")=="true"
    fun nativeSync(context:Context) {
        context.startActivity(Intent("com.ichi2.anki.DO_SYNC").setPackage("com.ichi2.anki").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
    fun history(context:Context,since:Long):List<JSONObject> {
        require(experimental(context)){"Stock AnkiDroid does not expose review history"}
        require(permitted(context)){"Grant AnkiDroid access first"}
        val out=mutableListOf<JSONObject>()
        val uri=Uri.parse("$ROOT/companion_revlog").buildUpon().appendQueryParameter("since",since.toString()).build()
        val cursor=context.contentResolver.query(uri,null,null,null,null) ?: error("AnkiDroid review-history bridge is unavailable")
        cursor.use {c->while(c.moveToNext())out.add(JSONObject().put("revlog_id",c.getLong(c.getColumnIndexOrThrow("id")))
            .put("card_id",c.getLong(c.getColumnIndexOrThrow("cid"))).put("duration_ms",c.getInt(c.getColumnIndexOrThrow("time")).coerceIn(0,600000)))}
        return out
    }
    fun configure(context:Context,settings:JSONObject):Boolean = try {
        require(experimental(context)){"Stock AnkiDroid does not expose companion_session"}
        val values=ContentValues().apply {
            put("parent_deck_id",settings.getString("parent_deck_id"));put("clearance",settings.getString("clearance"))
        }
        context.contentResolver.update(Uri.parse("$ROOT/companion_session"),values,null,null)>0
    } catch(e:Exception){false}
    fun open(context:Context,deckId:String) {
        val intent=Intent(Intent.ACTION_VIEW).setClassName("com.ichi2.anki","com.ichi2.anki.IntentHandler")
            .putExtra("EXTRA_DECK_ID",deckId.toLong()).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
    }
}
