// Personal Local helper. One dedicated namespace; no plaintext fallback or secrets in argv.
import Foundation
import Security
import LocalAuthentication
func fail(_ status: OSStatus) -> Never {
    FileHandle.standardError.write(Data("{\"code\":\"KEYCHAIN_OPERATION_FAILED\",\"os_status\":\(status)}\n".utf8))
    exit(42)
}
guard CommandLine.arguments.count == 3, getuid() != 0 else { fail(errSecParam) }
let operation = CommandLine.arguments[1]
let selector = CommandLine.arguments[2]
guard selector.range(of: "^[a-f0-9]{32}$", options: .regularExpression) != nil else { fail(errSecParam) }
let context = LAContext(); context.interactionNotAllowed = true
func query(_ suffix: String = "") -> [String: Any] {
    return [kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: "org.agentlibrarian.personal.session",
        kSecAttrAccount as String: selector + suffix,
        kSecUseAuthenticationContext as String: context]
}
func read(_ q: [String: Any]) -> Data {
    var request = q; request[kSecReturnData as String] = true
    request[kSecMatchLimit as String] = kSecMatchLimitOne
    var value: CFTypeRef?
    let status = SecItemCopyMatching(request as CFDictionary, &value)
    guard status == errSecSuccess, let data = value as? Data, data.count <= 65536 else { fail(status) }
    return data
}
func write(_ q: [String: Any], _ data: Data) {
    let status = SecItemUpdate(q as CFDictionary, [kSecValueData as String: data] as CFDictionary)
    if status == errSecItemNotFound {
        var item = q; item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let added = SecItemAdd(item as CFDictionary, nil)
        if added != errSecSuccess { fail(added) }
    } else if status != errSecSuccess { fail(status) }
}
switch operation {
case "probe":
    let q = query("-probe");let value = Data("SYNTHETIC_STORAGE_PROBE".utf8)
    write(q,value);guard read(q) == value else { fail(errSecDecode) }
    let status = SecItemDelete(q as CFDictionary);if status != errSecSuccess { fail(status) }
case "read": FileHandle.standardOutput.write(read(query()))
case "write":
    let data = FileHandle.standardInput.readData(ofLength: 65537)
    guard !data.isEmpty, data.count <= 65536,
          (try? JSONSerialization.jsonObject(with: data)) is [String: Any] else { fail(errSecParam) }
    write(query(),data)
case "delete":
    let status = SecItemDelete(query() as CFDictionary)
    if status != errSecSuccess && status != errSecItemNotFound { fail(status) }
default: fail(errSecParam)
}
