import { BrowserMultiFormatReader } from '@zxing/browser'
import { useEffect, useRef, useState } from 'react'

interface ScannerProps {
  onDetected: (isbn: string) => void
}

function isIsbn(text: string) {
  return /^97[89]\d{10}$/.test(text) || /^\d{9}[\dXx]$/.test(text)
}

export function Scanner({ onDetected }: ScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError(
        'Camera access is unavailable. Make sure the page is loaded over https:// or localhost.'
      )
      return
    }

    const reader = new BrowserMultiFormatReader()
    const controls = reader.decodeFromVideoDevice(
      undefined,
      videoRef.current!,
      (result) => {
        if (result) {
          const text = result.getText()
          if (isIsbn(text)) {
            onDetected(text)
          }
        }
      }
    )

    controls.catch((err) => {
      setError(err instanceof Error ? err.message : 'Could not access camera')
    })

    return () => {
      controls.then((c) => c.stop()).catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="scanner">
      {error ? (
        <p className="scanner-error">{error}</p>
      ) : (
        <video ref={videoRef} className="scanner-video" muted playsInline />
      )}
      <p className="scanner-hint">Point your camera at the barcode on the back of the book</p>
    </div>
  )
}
