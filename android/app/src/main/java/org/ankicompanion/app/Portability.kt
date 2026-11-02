package org.ankicompanion.app

import android.content.Context
import android.net.Uri
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.nio.charset.StandardCharsets
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

/**
 * Explicit, encrypted GUI recovery transfer for the exceptional case where
 * Android refuses a signing identity change. NOT used for ordinary updates.
 * The app's Android Keystore encryption key itself cannot be exported; decrypt
 * the old connection inside the original app, then re-encrypt the transfer
 * using a user-provided passphrase. No plaintext token is written to disk.
 */
object Portability {
    private const val MAX_BYTES=64*1024*1024
    private const val ITERATIONS=210_000
    private val random=SecureRandom()
    private fun b64(value:ByteArray)=Base64.encodeToString(value,Base64.NO_WRAP)
    private fun unb64(value:String)=Base64.decode(value,Base64.NO_WRAP)
    private fun derivedKey(passphrase:String,salt:ByteArray):SecretKeySpec {
        require(passphrase.length>=12){"Use a recovery passphrase of at least 12 characters"}
        val spec=PBEKeySpec(passphrase.toCharArray(),salt,ITERATIONS,256)
        val bytes=try {SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded}
            finally {spec.clearPassword()}
        return SecretKeySpec(bytes,"AES")
    }
    private val retainedPrefs=setOf("device_id","history_cursor","native_applied_revision",
        "native_generation","backfill_pending","bridge_status","sync_error","update_error",
        "ankidroid_update_error","last_seen_version")
    fun exportToBytes(context:Context,passphrase:String):ByteArray {
        val storage=Storage(context)
        val prefs=context.getSharedPreferences("companion",Context.MODE_PRIVATE)
        val saved=JSONObject()
        for((key,value) in prefs.all)if(key in retainedPrefs && value is String)saved.put(key,value)
        val content=JSONObject().put("schema",1).put("device_id",storage.deviceId)
            .put("connection",storage.connection() ?: JSONObject.NULL).put("preferences",saved)
        for(name in listOf("state.json","commands.json","update.json","ankidroid-update.json"))
            content.put(name,storage.load(name) ?: JSONObject.NULL)
        Outbox(context).use{content.put("outbox",it.exportTransfer())}
        val plaintext=content.toString().toByteArray(StandardCharsets.UTF_8)
        require(plaintext.size<=MAX_BYTES){"Recovery data exceeds safe transfer size"}
        val salt=ByteArray(16).also{random.nextBytes(it)}
        val iv=ByteArray(12).also{random.nextBytes(it)}
        val cipher=Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE,derivedKey(passphrase,salt),GCMParameterSpec(128,iv))
        val sealed=cipher.doFinal(plaintext)
        return JSONObject().put("format","AnkiCompanion-Encrypted-Recovery")
            .put("version",1).put("kdf","PBKDF2-HMAC-SHA256")
            .put("iterations",ITERATIONS).put("salt",b64(salt))
            .put("nonce",b64(iv)).put("ciphertext",b64(sealed))
            .toString().toByteArray(StandardCharsets.UTF_8)
    }
    fun restoreFromBytes(context:Context,encrypted:ByteArray,passphrase:String):Int {
        require(encrypted.size<=MAX_BYTES*2){"Recovery package too large"}
        val wrapper=JSONObject(String(encrypted,StandardCharsets.UTF_8))
        require(wrapper.getString("format")=="AnkiCompanion-Encrypted-Recovery" && wrapper.getInt("version")==1)
            {"Not a supported AnkiCompanion recovery package"}
        require(wrapper.getInt("iterations")==ITERATIONS && wrapper.getString("kdf")=="PBKDF2-HMAC-SHA256")
            {"Unsupported key derivation parameters"}
        val salt=unb64(wrapper.getString("salt"));val iv=unb64(wrapper.getString("nonce"))
        require(salt.size==16 && iv.size==12){"Invalid recovery header"}
        val cipher=Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE,derivedKey(passphrase,salt),GCMParameterSpec(128,iv))
        val plaintext=cipher.doFinal(unb64(wrapper.getString("ciphertext")))
        require(plaintext.size<=MAX_BYTES){"Invalid recovery body size"}
        val content=JSONObject(String(plaintext,StandardCharsets.UTF_8))
        require(content.getInt("schema")==1){"Unsupported recovery version"}
        val entries=content.getJSONArray("outbox")
        require(entries.length()<=250_000){"Recovery contains too many review records"}
        val storage=Storage(context)
        val currentConnection=storage.connection()
        val restoredConnection=content.optJSONObject("connection")
        require(currentConnection==null || restoredConnection==null ||
            currentConnection.optString("collection_id","primary")==restoredConnection.optString("collection_id","primary")) {
            "Recovery belongs to another collection; refusing to replace a paired installation"
        }
        // Restore local review IDs before connection/settings so a reconnect
        // can never silently omit pending unsent reviews after a crash.
        Outbox(context).use{it.restoreTransfer(entries)}
        val preferences=content.getJSONObject("preferences")
        val editor=context.getSharedPreferences("companion",Context.MODE_PRIVATE).edit()
        for(key in retainedPrefs)if(preferences.has(key))editor.putString(key,preferences.getString(key))
        editor.apply()
        for(name in listOf("state.json","commands.json","update.json","ankidroid-update.json"))
            content.optJSONObject(name)?.let{storage.save(name,it)}
        if(restoredConnection!=null)storage.saveConnection(restoredConnection)
        return entries.length()
    }
    fun exportToUri(context:Context,uri:Uri,passphrase:String) {
        val data=exportToBytes(context,passphrase)
        context.contentResolver.openOutputStream(uri,"wt")?.use{it.write(data)}
            ?: error("Recovery destination could not be opened")
    }
    fun restoreFromUri(context:Context,uri:Uri,passphrase:String):Int {
        val input=context.contentResolver.openInputStream(uri) ?: error("Recovery file cannot be opened")
        val bytes=input.use{source ->
            val out=java.io.ByteArrayOutputStream()
            val chunk=ByteArray(64*1024)
            while(true){val n=source.read(chunk);if(n<0)break
                require(out.size()+n<=MAX_BYTES*2){"Recovery file exceeds allowed size"}
                out.write(chunk,0,n)
            }
            out.toByteArray()
        }
        return restoreFromBytes(context,bytes,passphrase)
    }
}
