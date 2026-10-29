// Opt-in KN-OSS-04 personal pilot. Only approved Google auth rows; no database access.
// Chromium v10 format constants / schema-24 host binding are documented in
// THIRD_PARTY_NOTICES.md. Uses Apple's Security, CommonCrypto and CryptoKit APIs.
import Foundation
import Security
import CommonCrypto
import CryptoKit
func fail(_ code: String, _ status: OSStatus? = nil) -> Never {
    var message: [String: Any] = ["code": code]
    if let status = status { message["os_status"] = status }
    if let data = try? JSONSerialization.data(withJSONObject: message) { FileHandle.standardError.write(data) }
    exit(42)
}
guard getuid() != 0, CommandLine.arguments.count == 1 else { fail("BRAVE_BRIDGE_INVOCATION_INVALID") }
let raw = FileHandle.standardInput.readData(ofLength: 262145)
guard raw.count <= 262144,
    let input = try? JSONSerialization.jsonObject(with: raw) as? [String: Any],
    Set(input.keys) == Set(["schema_version", "records"]),
    let schema = input["schema_version"] as? Int, schema == 24,
    let records = input["records"] as? [[String: String]], !records.isEmpty, records.count <= 64 else { fail("BRAVE_COOKIE_PAYLOAD_INVALID") }
let names = Set(["SID","HSID","SSID","APISID","SAPISID","SIDCC","__Secure-1PSID","__Secure-3PSID","__Secure-1PSIDCC","__Secure-3PSIDCC","__Secure-1PSIDTS","__Secure-3PSIDTS"])
let hosts = Set([".google.com","google.com","notebooklm.google.com",".notebooklm.google.com","notebook.google.com",".notebook.google.com"])
let secondaryNames = Set(["OSID","LSID","__Host-GAPS","ACCOUNT_CHOOSER"])
let secondaryHosts = hosts.union(["accounts.google.com",".accounts.google.com"])
for row in records {
    guard Set(row.keys) == Set(["name","domain","path","secure","encrypted_value"]),
        let name = row["name"], let host = row["domain"],
        ((names.contains(name) && hosts.contains(host)) || (secondaryNames.contains(name) && secondaryHosts.contains(host))),
        row["path"] == "/", (row["secure"] == "true" || row["secure"] == "false"),
        (!(name.hasPrefix("__Secure-") || name.hasPrefix("__Host-")) || row["secure"] == "true"),
        let encoded = row["encrypted_value"], let data = Data(base64Encoded: encoded), data.count <= 16384,
        data.starts(with: Data("v10".utf8)), data.count > 3, (data.count - 3) % 16 == 0 else { fail("BRAVE_COOKIE_ENCRYPTION_UNSUPPORTED") }
}
// Exact item only; never enumerate Keychain. OS may ask the owner for permission.
let query: [String: Any] = [kSecClass as String:kSecClassGenericPassword,
    kSecAttrService as String:"Brave Safe Storage", kSecAttrAccount as String:"Brave",
    kSecReturnData as String:true, kSecMatchLimit as String:kSecMatchLimitOne]
var item: CFTypeRef?
let status = SecItemCopyMatching(query as CFDictionary, &item)
guard status == errSecSuccess, var password = item as? Data, !password.isEmpty, password.count <= 4096 else { fail("BRAVE_SAFE_STORAGE_UNAVAILABLE",status) }
var key = Data(count:16)
let salt = Array("saltysalt".utf8)
let derived = password.withUnsafeBytes { pw in
    key.withUnsafeMutableBytes { out in
        CCKeyDerivationPBKDF(CCPBKDFAlgorithm(kCCPBKDF2),pw.baseAddress!.assumingMemoryBound(to:CChar.self),password.count,
            salt,salt.count,CCPseudoRandomAlgorithm(kCCPRFHmacAlgSHA1),1003,out.baseAddress!.assumingMemoryBound(to:UInt8.self),16)
    }
}
password.resetBytes(in:0..<password.count)
guard derived == kCCSuccess else { fail("BRAVE_COOKIE_DERIVATION_FAILED") }
var output = [[String: Any]]()
for row in records {
    let encrypted = Data(base64Encoded:row["encrypted_value"]!)!.dropFirst(3)
    var plain = Data(count:encrypted.count + 16);var used = 0
    let iv = [UInt8](repeating:32,count:16)
    let decrypted = key.withUnsafeBytes { k in
        encrypted.withUnsafeBytes { c in
            plain.withUnsafeMutableBytes { p in
                CCCrypt(CCOperation(kCCDecrypt),CCAlgorithm(kCCAlgorithmAES),CCOptions(kCCOptionPKCS7Padding),
                    k.baseAddress,16,iv,c.baseAddress,encrypted.count,p.baseAddress,p.count,&used)
            }
        }
    }
    guard decrypted == kCCSuccess else { fail("BRAVE_COOKIE_DECRYPTION_FAILED") }
    plain.count = used
    let host = row["domain"]!;let digest = Data(SHA256.hash(data:Data(host.utf8)))
    guard plain.count > 32, plain.prefix(32) == digest,
        let value = String(data:plain.dropFirst(32),encoding:.utf8), !value.isEmpty else { fail("BRAVE_COOKIE_HOST_BINDING_INVALID") }
    output.append(["name":row["name"]!,"domain":host,"path":"/","secure":row["secure"] == "true","value":value])
    plain.resetBytes(in:0..<plain.count)
}
key.resetBytes(in:0..<key.count)
// Private parent pipe only. The caller must never log or expose this payload.
guard let encoded = try? JSONSerialization.data(withJSONObject:["cookies":output]), encoded.count <= 65536 else { fail("BRAVE_COOKIE_RESPONSE_LIMIT") }
FileHandle.standardOutput.write(encoded)
