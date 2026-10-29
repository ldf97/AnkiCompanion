package org.ankicompanion.app

import org.json.JSONObject
import org.json.JSONArray
import java.time.Instant
import java.time.ZoneId
import java.math.BigInteger
import java.security.MessageDigest

fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }

object Rules {
    fun day(timestamp: Long, zone: String, rollover: Int): String {
        val local = Instant.ofEpochMilli(timestamp).atZone(ZoneId.of(zone))
        val date = if (local.hour * 60 + local.minute < rollover) local.toLocalDate().minusDays(1) else local.toLocalDate()
        return date.toString()
    }
    fun lineup(day: String, skin: JSONObject, seed: String): JSONObject {
        fun pick(pool: JSONArray, key: String): Any {
            val message = listOf(seed,day,skin.getString("id"),skin.getString("version"),key).joinToString("\u001f")
            val digest = MessageDigest.getInstance("SHA-256").digest(message.toByteArray(Charsets.UTF_8))
            val index = BigInteger(1,digest.copyOfRange(0,8)).mod(BigInteger.valueOf(pool.length().toLong())).toInt()
            return pool.get(index)
        }
        val pools=skin.getJSONObject("background_pools");val shared=JSONObject()
        pools.keys().forEach { key -> shared.put(key,pick(pools.getJSONArray(key),"background:$key")) }
        val records=JSONObject()
        for(slot in skin.getJSONArray("time_slots").objects()+skin.getJSONObject("completion")) {
            val id=slot.getString("id");val quote=pick(slot.getJSONArray("quotes"),"$id:quote") as JSONObject
            val bg=slot.getJSONObject("background")
            val background=when(bg.getString("mode")) {
                "none" -> JSONObject.NULL
                "fixed" -> bg.getString("asset")
                "shared" -> shared.getString(bg.getString("pool"))
                else -> pick(pools.getJSONArray(bg.getString("pool")),"$id:background")
            }
            records.put(id,JSONObject().put("portrait",pick(slot.getJSONArray("portraits"),"$id:portrait"))
                .put("quote",quote.getString("text")).put("episode",quote.optString("source")).put("background",background))
        }
        return JSONObject().put("date",day).put("skin_id",skin.getString("id")).put("skin_version",skin.getString("version")).put("records",records)
    }
    fun slot(skin:JSONObject,minute:Int,completed:Boolean): JSONObject = if(completed) skin.getJSONObject("completion") else
        skin.getJSONArray("time_slots").objects().first { minute >= it.getInt("start_minute") && minute < it.getInt("end_minute") }
    fun tint(skin:JSONObject,minute:Int,completed:Boolean):Float {
        val s=skin.getJSONObject("style");val a=s.getInt("red_tint_start_minute");val b=s.getInt("red_tint_end_minute")
        return if(completed || minute<=a || minute>b) 0f else s.getDouble("max_red_tint").toFloat()*(minute-a)/(b-a)
    }
    fun next(decks:List<JSONObject>,parentId:String,mode:String):JSONObject? {
        val parent=decks.firstOrNull {it.getString("id")==parentId} ?: return null
        fun eligible(d:JSONObject)=d.getInt("new")>0 || (mode=="new_and_reviews" && d.getInt("review")+d.getInt("learning")>0)
        val prefix=parent.getString("name")+"::"
        fun natural(s:String)=Regex("\\d+").replace(s.lowercase()) {it.value.padStart(20,'0')}
        val children=decks.filter { val name=it.getString("name");name.startsWith(prefix) && !name.removePrefix(prefix).contains("::") }.sortedBy {natural(it.getString("name"))}
        return children.firstOrNull {eligible(it)} ?: parent.takeIf {eligible(it)}
    }
}
