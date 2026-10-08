// BarcodeDetector polyfill for browsers without a native one (iPhone Safari). ZXing-C++ compiled to WASM.
// Vendored from npm barcode-detector@3.2.2 ("pure" build, MIT) + zxing-wasm@3.1.3 reader (MIT); the .wasm is served
// from this folder instead of jsdelivr so scanning works without a third-party CDN.
import { BarcodeDetector, setZXingModuleOverrides } from "./bd-pure.mjs";
setZXingModuleOverrides({
  locateFile: (path, prefix) => path.endsWith(".wasm") ? new URL("./zxing_reader.wasm", import.meta.url).href : prefix + path,
});
export { BarcodeDetector };
