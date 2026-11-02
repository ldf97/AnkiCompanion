package org.ankicompanion.app

import android.content.Context
import android.net.Uri
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.nio.file.Files
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
    private const val MAX_SKIN_FILES=2000
    private const val MAX_SKIN_FILE_BYTES=20*1024*1024
    private fun digest(data:ByteArray)=MessageDigest.getInstance("SHA-256")
        .digest(data).joinToString(""){"%02x".format(it)}
    private fun safeRelative(path:String):Boolean = path.isNotEmpty() && path.length<=240 &&
        !path.startsWith("/") && !path.contains('\\') && !path.contains('\u0000') &&
        path.split('/').all{it.isNotEmpty() && it!="." && it!=".."}

    /** Include the original private skin bytes in encrypted exceptional recovery. */
    private fun exportPrivateSkins(context:Context):JSONArray {
        val base=File(context.filesDir,"packs").canonicalFile
        val entries=JSONArray()
        if(!base.isDirectory)return entries
        var total=0L
        for(file in base.walkTopDown()) {
            require(!Files.isSymbolicLink(file.toPath())){"Refusing symlinked skin data"}
            if(!file.isFile)continue
            val canonical=file.canonicalFile
            require(canonical.path.startsWith(base.path+File.separator)){"Skin file leaves private storage"}
            val relative=canonical.relativeTo(base).invariantSeparatorsPath
            require(safeRelative(relative)){"Unsupported private skin path"}
            require(entries.length()<MAX_SKIN_FILES){"Too many private skin files"}
            require(file.length()<=MAX_SKIN_FILE_BYTES){"Private skin file exceeds recovery limit"}
            val bytes=file.readBytes();total+=bytes.size
            require(total<=MAX_BYTES/2){"Private skins exceed encrypted recovery limit"}
            entries.put(JSONObject().put("path",relative).put("data",b64(bytes)).put("sha256",digest(bytes)))
        }
        return entries
    }

    private fun verifiedPrivateSkins(context:Context,content:JSONObject):List<Pair<File,ByteArray>> {
        val entries=content.optJSONArray("private_skin_files") ?: return emptyList() // older backups
        require(entries.length()<=MAX_SKIN_FILES){"Too many private skin files"}
        val base=File(context.filesDir,"packs").canonicalFile
        val restored=mutableListOf<Pair<File,ByteArray>>()
        val seen=mutableSetOf<String>()
        var total=0L
        for(i in 0 until entries.length()) {
            val item=entries.getJSONObject(i);val relative=item.getString("path")
            require(safeRelative(relative) && seen.add(relative)){"Duplicate or unsafe private skin path"}
            val file=File(base,relative).canonicalFile
            require(file.path.startsWith(base.path+File.separator)){"Skin recovery path escapes private storage"}
            val bytes=unb64(item.getString("data"));total+=bytes.size
            require(bytes.size<=MAX_SKIN_FILE_BYTES && total<=MAX_BYTES/2){"Skin recovery exceeds size limit"}
            require(digest(bytes)==item.getString("sha256")){"Private skin checksum mismatch"}
            require(!file.exists() || file.readBytes().contentEquals(bytes)){
                "Recovery would overwrite a different original private skin"}
            restored.add(file to bytes)
        }
        return restored
    }

    private fun restorePrivateSkins(files:List<Pair<File,ByteArray>>) {
        for((file,bytes) in files) {
            if(file.exists())continue // byte-identical original already present
            require(file.parentFile!!.mkdirs() || file.parentFile!!.isDirectory){"Cannot create skin directory"}
            val temp=File.createTempFile("recovery-", ".partial", file.parentFile)
            try {
                temp.writeBytes(bytes)
                check(temp.renameTo(file)){"Could not restore original private skin"}
            } finally {temp.delete()}
        }
    }

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
        content.put("private_skin_files",exportPrivateSkins(context))
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
        // Validate every private file BEFORE altering settings or offline outbox.
        val skins=verifiedPrivateSkins(context,content)
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
        check(editor.commit()){"Could not restore stored review cursors"}
        for(name in listOf("state.json","commands.json","update.json","ankidroid-update.json"))
            content.optJSONObject(name)?.let{storage.save(name,it)}
        if(restoredConnection!=null)storage.saveConnection(restoredConnection)
        restorePrivateSkins(skins)
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
