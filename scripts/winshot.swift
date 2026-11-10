// prints the CGWindowID of the biggest layer 0 window a process has on screen
import CoreGraphics
import Foundation
let want = CommandLine.arguments[1]
let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as! [[String: Any]]
var best: (Int, Double) = (0, 0)
for w in list where (w[kCGWindowOwnerName as String] as? String) == want && (w[kCGWindowLayer as String] as? Int) == 0 {
    let b = w[kCGWindowBounds as String] as! [String: Double]
    let area = b["Width"]! * b["Height"]!
    FileHandle.standardError.write("\(w[kCGWindowNumber as String]!) \(b)\n".data(using: .utf8)!)
    if area > best.1 { best = (w[kCGWindowNumber as String] as! Int, area) }
}
print(best.0)
