import React, { useState, useRef, useEffect } from 'react';
import { Camera, Search, Package, X, QrCode } from 'lucide-react';

const getApiBase = () => (typeof window !== 'undefined' ? window.location.origin : '');
const getToken = () => {
  try {
    return localStorage.getItem('retailos_token') || localStorage.getItem('token') || '';
  } catch {
    return '';
  }
};
const headers = () => ({
  Authorization: `Bearer ${getToken()}`,
  'Content-Type': 'application/json',
});

export default function BarcodeScannerTab() {
  const api = getApiBase();
  const [scanning, setScanning] = useState(false);
  const [manualCode, setManualCode] = useState('');
  const [result, setResult] = useState(null);
  const [searchResults, setSearchResults] = useState([]);
  const [error, setError] = useState('');
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  // Cleanup camera on unmount
  useEffect(() => {
    return () => stopCamera();
  }, []);

  const startCamera = async () => {
    setError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setScanning(true);
    } catch (err) {
      setError('Camera access denied. Use manual entry instead.');
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setScanning(false);
  };

  const lookupBarcode = async (code) => {
    if (!code) return;
    setError('');
    setResult(null);

    try {
      const resp = await fetch(`${api}/api/mobile/barcode/${encodeURIComponent(code)}`, {
        headers: headers(),
      });
      const data = await resp.json();
      if (data.found) {
        setResult(data);
      } else {
        setError(`No product found for barcode: ${code}`);
      }
    } catch {
      setError('Failed to lookup barcode. Check your connection.');
    }
  };

  const searchProducts = async (query) => {
    if (!query || query.length < 2) {
      setSearchResults([]);
      return;
    }
    try {
      const resp = await fetch(
        `${api}/api/mobile/barcode/search?q=${encodeURIComponent(query)}`,
        { headers: headers() }
      );
      const data = await resp.json();
      setSearchResults(data.results || []);
    } catch {
      setSearchResults([]);
    }
  };

  const handleManualSubmit = (e) => {
    e.preventDefault();
    if (manualCode.trim()) {
      lookupBarcode(manualCode.trim());
    }
  };

  // Use BarcodeDetector API if available (Chrome 83+, Android)
  useEffect(() => {
    if (!scanning || !videoRef.current) return;

    if (!('BarcodeDetector' in window)) {
      return; // Fall back to manual entry
    }

    const detector = new window.BarcodeDetector({
      formats: ['ean_13', 'ean_8', 'code_128', 'code_39', 'upc_a', 'upc_e', 'qr_code'],
    });

    let animationId;
    const detect = async () => {
      if (!videoRef.current || !scanning) return;
      try {
        const barcodes = await detector.detect(videoRef.current);
        if (barcodes.length > 0) {
          const code = barcodes[0].rawValue;
          setManualCode(code);
          lookupBarcode(code);
          stopCamera();
          return;
        }
      } catch {
        // Ignore detection errors
      }
      animationId = requestAnimationFrame(detect);
    };

    // Start detection after video is playing
    const onPlaying = () => {
      animationId = requestAnimationFrame(detect);
    };
    videoRef.current.addEventListener('playing', onPlaying);

    return () => {
      cancelAnimationFrame(animationId);
      if (videoRef.current) {
        videoRef.current.removeEventListener('playing', onPlaying);
      }
    };
  }, [scanning]);

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-xl font-bold text-white flex items-center gap-2">
        <QrCode size={20} /> Barcode Scanner
      </h2>

      {/* Camera / Scanner */}
      <div className="bg-gray-800 rounded-lg p-4">
        {!scanning ? (
          <div className="text-center">
            <button
              onClick={startCamera}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg flex items-center gap-2 mx-auto"
            >
              <Camera size={20} /> Open Camera Scanner
            </button>
            <p className="text-gray-400 text-sm mt-2">
              Point your phone camera at a barcode to scan
            </p>
          </div>
        ) : (
          <div className="relative">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              className="w-full max-h-64 rounded-lg bg-black"
            />
            {/* Scanning overlay */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="border-2 border-green-400 w-48 h-32 rounded-lg opacity-60" />
            </div>
            <button
              onClick={stopCamera}
              className="absolute top-2 right-2 bg-red-600 text-white p-1 rounded-full"
            >
              <X size={16} />
            </button>
            {!('BarcodeDetector' in window) && (
              <p className="text-yellow-400 text-xs mt-2">
                Browser barcode detection not supported. Enter code manually below.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Manual Entry / Search */}
      <div className="bg-gray-800 rounded-lg p-4">
        <form onSubmit={handleManualSubmit} className="flex gap-3">
          <input
            className="flex-1 bg-gray-700 text-white px-4 py-2 rounded text-sm"
            placeholder="Enter barcode or product name..."
            value={manualCode}
            onChange={(e) => {
              setManualCode(e.target.value);
              searchProducts(e.target.value);
            }}
          />
          <button
            type="submit"
            className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded text-sm flex items-center gap-1"
          >
            <Search size={16} /> Lookup
          </button>
        </form>

        {/* Search Suggestions */}
        {searchResults.length > 0 && !result && (
          <div className="mt-2 bg-gray-700 rounded-lg overflow-hidden">
            {searchResults.map((p, i) => (
              <button
                key={i}
                className="w-full text-left px-4 py-2 hover:bg-gray-600 border-b border-gray-600 last:border-0"
                onClick={() => {
                  setResult({ ...p, found: true });
                  setSearchResults([]);
                }}
              >
                <div className="text-white text-sm">{p.product_name}</div>
                <div className="text-gray-400 text-xs">
                  {p.sku} | ₹{(p.unit_price || 0).toFixed(2)} | Stock: {p.current_stock}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="bg-gray-800 rounded-lg p-5">
          <div className="flex items-start gap-4">
            <div className="bg-gray-700 p-3 rounded-lg">
              <Package size={32} className="text-blue-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-white text-lg font-bold">{result.product_name}</h3>
              <div className="grid grid-cols-2 gap-3 mt-3 text-sm">
                <div>
                  <span className="text-gray-400">SKU:</span>{' '}
                  <span className="text-white font-mono">{result.sku}</span>
                </div>
                <div>
                  <span className="text-gray-400">Category:</span>{' '}
                  <span className="text-white">{result.category}</span>
                </div>
                <div>
                  <span className="text-gray-400">Price:</span>{' '}
                  <span className="text-green-400 font-bold">₹{(result.unit_price || 0).toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-gray-400">Stock:</span>{' '}
                  <span className={result.current_stock > 0 ? 'text-green-400' : 'text-red-400'}>
                    {result.current_stock} units
                  </span>
                </div>
                {result.barcode && (
                  <div className="col-span-2">
                    <span className="text-gray-400">Barcode:</span>{' '}
                    <span className="text-white font-mono">{result.barcode}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
          <button
            className="mt-4 text-gray-400 text-sm hover:text-white"
            onClick={() => {
              setResult(null);
              setManualCode('');
            }}
          >
            Clear result
          </button>
        </div>
      )}
    </div>
  );
}
