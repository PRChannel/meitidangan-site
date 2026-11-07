// macOS 本地 OCR：用 Vision 框架识别中文图片文本。
// 编译：swiftc -O tools/ocr_image.swift -o /tmp/ocr
// 用法：/tmp/ocr <图片路径> [--tile 3000] [--box] [--crop x,y,w,h] [--scale 2]
//   超长竖图会按 --tile 高度切片识别后顺序拼接，避免单次请求过大。
//   --box 输出「文本<TAB>x<TAB>y<TAB>w<TAB>h」，坐标为像素、原点左上，供表格重建使用。
//   --crop 只识别指定矩形（原点左上），输出坐标仍为整图坐标。
//   --scale 识别前放大倍数，小字表格放大后更准。
import Foundation
import Vision
import AppKit

func scaleImage(_ cg: CGImage, _ factor: CGFloat) -> CGImage {
    if factor == 1 { return cg }
    let w = Int(CGFloat(cg.width) * factor), h = Int(CGFloat(cg.height) * factor)
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return cg }
    ctx.interpolationQuality = .high
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
    return ctx.makeImage() ?? cg
}

func ocr(_ cg: CGImage, withBox: Bool) -> [(String, CGRect)] {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    req.usesLanguageCorrection = false
    req.minimumTextHeight = 0.0
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch { return [] }
    let W = CGFloat(cg.width), H = CGFloat(cg.height)
    var out: [(String, CGRect)] = []
    for obs in (req.results ?? []) {
        guard let c = obs.topCandidates(1).first else { continue }
        let b = obs.boundingBox  // 归一化，原点左下
        // 转像素坐标并把 y 翻到左上原点
        let rect = CGRect(x: b.minX * W, y: (1 - b.maxY) * H, width: b.width * W, height: b.height * H)
        out.append((c.string, rect))
    }
    return out.sorted { a, b in
        if abs(a.1.midY - b.1.midY) > 8 { return a.1.midY < b.1.midY }
        return a.1.minX < b.1.minX
    }
}

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("用法: ocr <图片路径> [--tile 高度] [--box]\n".data(using: .utf8)!)
    exit(2)
}
let path = args[1]
var tile = 3000
if let i = args.firstIndex(of: "--tile"), i + 1 < args.count, let v = Int(args[i + 1]) { tile = v }
var scale: CGFloat = 1
if let i = args.firstIndex(of: "--scale"), i + 1 < args.count, let v = Double(args[i + 1]) { scale = CGFloat(v) }
var cropRect: CGRect? = nil
if let i = args.firstIndex(of: "--crop"), i + 1 < args.count {
    let p = args[i + 1].split(separator: ",").compactMap { Int($0) }
    if p.count == 4 { cropRect = CGRect(x: p[0], y: p[1], width: p[2], height: p[3]) }
}
let withBox = args.contains("--box")

guard let img = NSImage(contentsOfFile: path),
      var cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("无法读取图片: \(path)\n".data(using: .utf8)!)
    exit(1)
}

var originX: CGFloat = 0, originY: CGFloat = 0
if let r = cropRect, let sub = cg.cropping(to: r) {
    cg = sub
    originX = r.minX
    originY = r.minY
}
if scale != 1 { cg = scaleImage(cg, scale) }

func emit(_ line: String, _ rect: CGRect, _ yOffset: CGFloat) {
    let x = rect.minX / scale + originX
    let y = (rect.minY + yOffset) / scale + originY
    if withBox {
        print("\(line)\t\(Int(x))\t\(Int(y))\t\(Int(rect.width / scale))\t\(Int(rect.height / scale))")
    } else {
        print(line)
    }
}

let h = cg.height
if h <= tile {
    for (s, r) in ocr(cg, withBox: withBox) { emit(s, r, 0) }
} else {
    var y = 0
    while y < h {
        let th = min(tile, h - y)
        // 切片之间保留 40px 重叠，避免行被切断
        let overlap = (y + th < h) ? 40 : 0
        if let sub = cg.cropping(to: CGRect(x: 0, y: y, width: cg.width, height: th)) {
            for (s, r) in ocr(sub, withBox: withBox) { emit(s, r, CGFloat(y)) }
        }
        y += th - overlap
    }
}

