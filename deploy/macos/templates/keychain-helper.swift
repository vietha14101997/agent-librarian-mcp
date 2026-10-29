// Owner-built service helper; no invocation during automatic tests.
// Security.framework stores one generic-password item. No file fallback or UI prompt.
import Foundation
import Security
import LocalAuthentication

let name = "org.agentlibrarian.research.session"
let account = "service-session-v1"
func fail() -> Never { exit(42) }
guard CommandLine.arguments.count == 2, getuid() != 0 else { fail() }
let op = CommandLine.arguments[1]
let context = LAContext()
context.interactionNotAllowed = true
var query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: name, kSecAttrAccount as String: account,
    kSecUseAuthenticationContext as String: context]
switch op {
case "read":
    query[kSecReturnData as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
          let data = result as? Data, !data.isEmpty, data.count <= 65536 else { fail() }
    FileHandle.standardOutput.write(data)
case "write":
    let data = FileHandle.standardInput.readData(ofLength: 65537)
    guard !data.isEmpty, data.count <= 65536,
          (try? JSONSerialization.jsonObject(with: data)) is [String: Any] else { fail() }
    let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
    if status == errSecItemNotFound {
        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        guard SecItemAdd(query as CFDictionary, nil) == errSecSuccess else { fail() }
    } else if status != errSecSuccess { fail() }
case "delete":
    let status = SecItemDelete(query as CFDictionary)
    guard status == errSecSuccess || status == errSecItemNotFound else { fail() }
default: fail()
}
