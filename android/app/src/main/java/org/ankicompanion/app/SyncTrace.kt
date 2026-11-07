package org.ankicompanion.app

import org.json.JSONArray
import org.json.JSONObject

/** Small, durable, app-owned diagnostic history. Never record pairing credentials. */
object SyncTrace {
    fun redact(message:String,config:JSONObject?):String {
        var value=message
        val token=config?.optString("token","") ?: ""
        if(token.isNotBlank())value=value.replace(token,"[REDACTED TOKEN]")
        value=value.replace(Regex("(?i)(token|password|authorization|secret)=([^&\\s]+)"),"$1=[REDACTED]")
        value=value.replace(Regex("(?i)Bearer\\s+[A-Za-z0-9._~+/-]+"),"Bearer [REDACTED]")
        return value.take(400)
    }
    fun record(store:Storage,stage:String,detail:String="") {
        try {
            synchronized(this) {
                val history=store.load("sync-trace.json")?.optJSONArray("events") ?: JSONArray()
                val next=JSONArray()
                val start=(history.length()-39).coerceAtLeast(0)
                for(i in start until history.length())next.put(history.getJSONObject(i))
                val safe=redact(detail,store.connection())
                next.put(JSONObject().put("at_ms",System.currentTimeMillis())
                    .put("stage",stage.take(70)).put("detail",safe))
                store.save("sync-trace.json",JSONObject().put("events",next))
                store.setSetting("sync_stage",stage.take(70))
            }
        }catch(_:Exception) {
            // Diagnostics must never interrupt studying or event delivery.
        }
    }
}
