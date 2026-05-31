import { useEffect, useRef, useState } from "react";

import { recognizeAudio } from "../../api/client";
import { USE_MOCK } from "../../lib/env";
import type { RecognitionResult } from "../../types/api";

type Status =
  | "idle"
  | "recording"
  | "recognizing"
  | "result"
  | "nomatch"
  | "error";

// 録音の最大長 (ms)。AudD は ~12-15 秒あれば十分に指紋照合できる。
const MAX_RECORDING_MS = 12_000;

// MediaRecorder が出力する mime を環境ごとに feature-detect する。
// Chrome/Firefox は webm/ogg + opus、iOS Safari は mp4/aac。AudD は両方受理する。
function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
    "audio/aac",
  ];
  return candidates.find((t) => MediaRecorder.isTypeSupported(t));
}

// secure context (https / localhost) + API 存在を確認する。PWA / iOS では
// 非対応・非セキュアだと getUserMedia 自体が無いか reject するので事前に弾く。
function isRecordingSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof MediaRecorder !== "undefined" &&
    (window.isSecureContext ?? false)
  );
}

type Props = {
  // 認識結果を「On the hunt に追加」する。DiggingPage が artist フォールバック +
  // RecordFormModal prefill を担う。
  onAdd: (result: RecognitionResult) => void;
};

export function ListenPanel({ onAdd }: Props) {
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [result, setResult] = useState<RecognitionResult | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const stopTimerRef = useRef<number | null>(null);
  const tickRef = useRef<number | null>(null);
  // Cancel 時は onstop で認識へ進めず破棄するためのフラグ。
  const canceledRef = useRef(false);

  // demo (USE_MOCK) ではマイクを使わず固定のサンプル結果を返すので、録音対応の
  // 有無に関わらず操作可能にする (採用担当の環境にマイクが無くても showcase が動く)。
  const supported = USE_MOCK || isRecordingSupported();
  const spinning = status === "recording" || status === "recognizing";

  // unmount 時にマイクと録音を確実に止める (常時 ON 防止)。
  useEffect(() => {
    return () => {
      if (stopTimerRef.current !== null) window.clearTimeout(stopTimerRef.current);
      if (tickRef.current !== null) window.clearInterval(tickRef.current);
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  function releaseStream() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  function clearTimers() {
    if (stopTimerRef.current !== null) {
      window.clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
  }

  async function handleRecognize(blob: Blob) {
    setStatus("recognizing");
    try {
      const r = await recognizeAudio(blob);
      if (!r.matched) {
        setStatus("nomatch");
        return;
      }
      setResult(r);
      setStatus("result");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }

  async function startRecording() {
    setErrorMsg(null);
    setResult(null);
    setElapsed(0);
    // demo: マイク録音を丸ごとスキップし、Tap で即「認識中 → サンプル結果」へ。
    // recognizeAudio (mock) は blob を無視して固定結果を返すので空 blob で良い。
    if (USE_MOCK) {
      void handleRecognize(new Blob());
      return;
    }
    // 許可ダイアログはユーザー操作 (このクリック) のタイミングで初めて呼ぶ。
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      // NotAllowedError = ユーザーが拒否 / NotFoundError = デバイス無し。
      const name = err instanceof DOMException ? err.name : "";
      setErrorMsg(
        name === "NotAllowedError"
          ? "マイクの使用が許可されていません。ブラウザ／OS の設定でこのアプリのマイクを許可してください（iOS は 設定 > 対象アプリ > マイク）。"
          : name === "NotFoundError"
            ? "マイクが見つかりませんでした。"
            : "マイクを起動できませんでした。",
      );
      setStatus("error");
      return;
    }
    streamRef.current = stream;
    chunksRef.current = [];
    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recorderRef.current = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      clearTimers();
      releaseStream();
      // Cancel 経由なら録音データを破棄して idle に戻す (認識へ進めない)。
      if (canceledRef.current) {
        canceledRef.current = false;
        chunksRef.current = [];
        setStatus("idle");
        return;
      }
      const blob = new Blob(chunksRef.current, {
        type: mimeType ?? "audio/webm",
      });
      void handleRecognize(blob);
    };
    canceledRef.current = false;
    recorder.start();
    setStatus("recording");
    // 経過秒カウンタ。
    tickRef.current = window.setInterval(() => {
      setElapsed((e) => e + 1);
    }, 1000);
    // 一定時間で自動停止。手動停止 (stopRecording) でもクリアする。
    stopTimerRef.current = window.setTimeout(() => {
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    }, MAX_RECORDING_MS);
  }

  function stopRecording() {
    clearTimers();
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }

  // 録音を破棄して待機状態へ。onstop で canceledRef を見て認識をスキップする。
  function cancelRecording() {
    canceledRef.current = true;
    clearTimers();
    setElapsed(0);
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    } else {
      // すでに止まっている場合のフォールバック。
      releaseStream();
      chunksRef.current = [];
      setStatus("idle");
    }
  }

  function reset() {
    setResult(null);
    setErrorMsg(null);
    setElapsed(0);
    setStatus("idle");
  }

  // レコード盤の中央レーベルに出す内容。
  function centerLabel() {
    if (status === "result" && result?.image_url) {
      return (
        <img
          src={result.image_url}
          alt=""
          className="h-full w-full rounded-full object-cover"
        />
      );
    }
    if (status === "recording") {
      return (
        <div className="flex flex-col items-center gap-1 text-paper">
          <span className="h-2.5 w-2.5 rounded-full bg-[#c0392b] [animation:var(--animate-rec-pulse)]" />
          <span className="font-mono text-[11px] tabular-nums tracking-tight">
            0:{String(elapsed).padStart(2, "0")}
          </span>
        </div>
      );
    }
    // 認識中は回転だけで「読んでいる」感を出し、盤面にテキストは出さない。
    if (status === "recognizing") {
      return null;
    }
    if (status === "result") {
      // 結果はあるが画像なし → レーベル風テキスト
      return (
        <span className="px-2 text-center text-[9px] uppercase leading-tight tracking-wider text-paper/70">
          {result?.artist_name ?? "—"}
        </span>
      );
    }
    // nomatch / error / idle はレーベルを無地のままにする (盤面テキストを避ける)。
    return null;
  }

  const tappable = status === "idle" || status === "nomatch" || status === "error";

  if (!supported) {
    return (
      <div className="mt-8 text-center text-sm italic text-ink-mute">
        この環境では録音に対応していません。
        <br />
        https 接続とマイク対応ブラウザが必要です。
      </div>
    );
  }

  return (
    <div
      data-tour="listen-area"
      className="mx-auto flex w-fit flex-col items-center pt-2"
    >
      {/* レコードプレーヤー風のステージ。
          サイズは単一固定 (sm: で拡大しない)。盤とトーンアームの位置関係を px で
          固定し、画面幅が変わっても針が必ず溝の上に着地するようにするため。 */}
      <div
        data-tour="listen-disc"
        className="relative mt-4 flex h-72 w-72 items-center justify-center"
      >
        {/* トーンアーム: ステージ基準で配置 (盤と同じ固定座標系)。 */}
        <Tonearm engaged={spinning} />

        {/* レコード盤本体 (クリックで録音開始) */}
        <button
          type="button"
          onClick={
            status === "recording"
              ? stopRecording
              : tappable
                ? startRecording
                : undefined
          }
          disabled={status === "recognizing"}
          aria-label={
            status === "recording" ? "録音を停止" : "録音して認識"
          }
          className={`group relative h-64 w-64 rounded-full ${
            tappable || status === "recording"
              ? "cursor-pointer"
              : "cursor-default"
          }`}
        >
          <Disc spinning={spinning}>{centerLabel()}</Disc>
        </button>
      </div>

      {/* キャプション / アクション */}
      <div className="mt-8 flex min-h-[5.5rem] flex-col items-center gap-3 text-center">
        {status === "idle" && (
          <>
            <p className="max-w-xs text-sm italic leading-relaxed text-ink-mute">
              Tap Vinyle !
            </p>
            {USE_MOCK && (
              <p className="max-w-xs text-xs italic leading-relaxed text-ink-faint">
                demo — 録音せずサンプル音源で認識します
              </p>
            )}
          </>
        )}

        {status === "recording" && (
          <>
            <Waveform />
            <p className="text-[13px] uppercase tracking-[0.32em] text-ink-mute">
              Listening
            </p>
            {/* 12 秒で自動検索されるので、どちらも控えめなテキストボタンにする。
                規約どおり副次 (Cancel) を左、Search now を右に。 */}
            <div className="mt-1 flex items-center gap-6">
              <button
                type="button"
                onClick={cancelRecording}
                className="cursor-pointer text-sm italic text-ink-mute transition-colors hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={stopRecording}
                className="cursor-pointer border-b border-ink/40 pb-0.5 text-sm tracking-wide text-ink transition-colors hover:border-ink"
              >
                Search now
              </button>
            </div>
          </>
        )}

        {status === "recognizing" && (
          <>
            <Waveform />
            <p className="text-[13px] uppercase tracking-[0.32em] text-ink-mute">
              Reading the groove
            </p>
          </>
        )}

        {status === "result" && result && (
          <>
            {/* ジャケットは盤の中央レーベルに表示済みなので、ここはテキストのみ。 */}
            <div className="max-w-sm">
              <div className="truncate text-lg font-medium leading-snug text-ink">
                {result.title}
              </div>
              <div className="mt-0.5 truncate text-sm italic text-ink-mute">
                {result.artist_name}
              </div>
              {result.album && result.album !== result.title && (
                <div className="mt-0.5 truncate text-xs italic text-ink-faint">
                  {result.album}
                </div>
              )}
            </div>
            {/* アプリ規約: 副次 (Try again=録り直し) を左、主アクション (追加) を右に。
                Try again は古い録音を棄却して即再録音する (nomatch と挙動・文言を統一)。 */}
            <div className="mt-1 flex items-center gap-5">
              <button
                type="button"
                onClick={startRecording}
                className="cursor-pointer text-sm italic text-ink-mute transition-colors hover:text-ink"
              >
                Try again
              </button>
              <button
                type="button"
                onClick={() => onAdd(result)}
                className="cursor-pointer bg-ink px-5 py-2 text-sm tracking-wide text-paper transition-opacity hover:opacity-85"
              >
                To the hunt
              </button>
            </div>
          </>
        )}

        {status === "nomatch" && (
          <>
            {/* 音声検索ユーザーは曲名を知らないのが前提なので手動追加は誘導しない。
                録り直しで拾えることは実際あるため、シンプルに再挑戦を促す。 */}
            <p className="text-sm italic text-ink-mute">Sorry, no match...</p>
            {/* 規約どおり副次 (Cancel=Listen 待機へ戻る) を左、Try again を右に。 */}
            <div className="mt-1 flex items-center gap-5">
              <button
                type="button"
                onClick={reset}
                className="cursor-pointer text-sm italic text-ink-mute transition-colors hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={startRecording}
                className="cursor-pointer border-b border-ink/40 pb-0.5 text-sm tracking-wide text-ink transition-colors hover:border-ink"
              >
                Try again
              </button>
            </div>
          </>
        )}

        {status === "error" && (
          <>
            <p className="max-w-xs text-sm italic leading-relaxed text-ink-mute">
              {errorMsg ?? "エラーが発生しました。"}
            </p>
            <button
              type="button"
              onClick={reset}
              className="cursor-pointer border-b border-ink/40 pb-0.5 text-sm tracking-wide text-ink transition-colors hover:border-ink"
            >
              もう一度
            </button>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * レコード盤。CSS の繰り返し radial/conic グラデーションで溝・光沢・レーベルを表現。
 * spinning=true の間だけ 33⅓ RPM 風に回転する。
 */
function Disc({
  spinning,
  children,
}: {
  spinning: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`vinyl-disc absolute inset-0 rounded-full shadow-[0_18px_40px_-12px_rgba(26,23,20,0.55)] ${
        spinning ? "[animation:var(--animate-vinyl-spin)]" : ""
      }`}
      style={{
        background: [
          // 盤の地色 (ほぼ黒、わずかに温かみ)
          "radial-gradient(circle at center, #14110f 0%, #14110f 30%, #1c1815 30.2%, #14110f 100%)",
          // 溝: 細かい同心円
          "repeating-radial-gradient(circle at center, rgba(255,255,255,0.045) 0px, rgba(255,255,255,0.045) 1px, rgba(0,0,0,0) 1.5px, rgba(0,0,0,0) 3px)",
          // 光沢: 斜めのハイライト帯
          "conic-gradient(from 210deg at 50% 50%, rgba(255,255,255,0) 0deg, rgba(255,255,255,0.10) 35deg, rgba(255,255,255,0) 80deg, rgba(255,255,255,0) 200deg, rgba(255,255,255,0.06) 235deg, rgba(255,255,255,0) 280deg)",
        ].join(", "),
      }}
    >
      {/* 外周のリム */}
      <div className="absolute inset-0 rounded-full ring-1 ring-inset ring-white/10" />

      {/* 中央レーベル */}
      <div className="absolute left-1/2 top-1/2 flex h-[38%] w-[38%] -translate-x-1/2 -translate-y-1/2 items-center justify-center overflow-hidden rounded-full bg-[#b8442e] shadow-[inset_0_0_0_1px_rgba(0,0,0,0.25)]">
        {/* レーベルの紙質感 (淡いリング) */}
        <div className="pointer-events-none absolute inset-0 rounded-full bg-[repeating-radial-gradient(circle_at_center,rgba(0,0,0,0.06)_0px,rgba(0,0,0,0.06)_1px,transparent_2px,transparent_5px)]" />
        <div className="relative z-10 flex h-full w-full items-center justify-center">
          {children}
        </div>
      </div>

      {/* スピンドル穴 (回転していない時のみ中心の穴が見える / 画像時は隠す) */}
      <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#14110f] ring-1 ring-white/15" />
    </div>
  );
}

/**
 * トーンアーム。engaged=true で盤の上に回り込む (針が降りる) ように傾く。
 * 紙トーンに合わせたインク色の細い意匠。
 */
function Tonearm({ engaged }: { engaged: boolean }) {
  // ステージ (h-72 = 288px, 固定) を基準にした px 配置。サイズを単一固定にしたので
  // px のままで全環境で針が同じ位置 (盤の溝の上) に着地する。engaged で内側へ降りる。
  return (
    <div className="pointer-events-none absolute -right-1 -top-1 z-20 h-28 w-28">
      {/* ピボット基部 */}
      <div className="absolute right-1 top-1 h-6 w-6 rounded-full bg-ink shadow-[0_2px_6px_rgba(0,0,0,0.4)]">
        <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-paper/70" />
      </div>
      {/* アーム本体: engaged で内側へ回り込む */}
      <div
        className="absolute right-[14px] top-[14px] origin-top-right transition-transform duration-700 ease-out"
        style={{ transform: engaged ? "rotate(30deg)" : "rotate(-6deg)" }}
      >
        <div className="h-[92px] w-[3px] rounded-full bg-gradient-to-b from-ink to-ink/70" />
        {/* ヘッドシェル + 針 */}
        <div className="absolute -bottom-2 -left-[5px] h-4 w-[13px] -rotate-12 rounded-sm bg-ink shadow-[0_2px_4px_rgba(0,0,0,0.35)]" />
      </div>
    </div>
  );
}

/**
 * 録音 / 認識中のサウンド可視化。インク色の細いバーが波打つ。
 * 各バーに異なる animation-delay / duration を与えて自然な揺らぎにする。
 */
function Waveform() {
  // 中央が高く端が低い、対称的な波形プロファイル。
  const bars = [0.45, 0.7, 1, 0.6, 0.9, 0.5, 0.75, 1, 0.55, 0.8, 0.4];
  return (
    <div className="flex h-7 items-center justify-center gap-[3px]" aria-hidden>
      {bars.map((h, i) => (
        <span
          key={i}
          className="w-[2px] rounded-full bg-ink/70"
          style={{
            height: `${h * 100}%`,
            transformOrigin: "center",
            animation: `wave-bar ${0.7 + (i % 3) * 0.18}s ease-in-out ${i * 0.08}s infinite`,
          }}
        />
      ))}
    </div>
  );
}
