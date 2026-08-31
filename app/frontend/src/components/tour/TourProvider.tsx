import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { USE_MOCK } from "../../lib/env";
import { TOUR_STEPS } from "./steps";
import type { TourStep } from "./steps";

// ============================================================================
// demo 機能ツアー
//   - demo (Enter demo) でアプリに入るたびに自動起動する。
//   - TopNav の「tour」ボタンからいつでも再生できる。
//   - 各ステップでルートを遷移しつつ対象要素をスポットライトし、吹き出しで解説。
//   - 自作・依存追加なし。アプリの紙トーン / セリフ体の世界観に合わせる。
// ============================================================================

type TourCtx = {
  /** ツアーを最初から開始する。 */
  start: () => void;
  /** 自動起動が有効か (TopNav のボタン表示判定に使う想定だが現状は常設)。 */
  available: boolean;
};

const TourContext = createContext<TourCtx>({ start: () => {}, available: false });

export function useTour(): TourCtx {
  return useContext(TourContext);
}

export function TourProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  // null = 非アクティブ。数値 = 現在のステップ index。
  const [index, setIndex] = useState<number | null>(null);
  const active = index !== null;

  const start = useCallback(() => setIndex(0), []);

  const stop = useCallback(() => setIndex(null), []);

  const next = useCallback(() => {
    setIndex((i) => {
      if (i === null) return i;
      if (i >= TOUR_STEPS.length - 1) return null;
      return i + 1;
    });
  }, []);

  const prev = useCallback(
    () => setIndex((i) => (i === null ? i : Math.max(0, i - 1))),
    [],
  );

  // demo でアプリに入るたびに自動起動する (Enter demo → ツアー開始)。
  // TourProvider は認証後 (AppLayout) にマウントされるので、ここに来た時点で
  // 「demo に入った」と見なせる。
  useEffect(() => {
    if (!USE_MOCK) return;
    const t = window.setTimeout(() => setIndex(0), 700);
    return () => window.clearTimeout(t);
  }, []);

  // ステップが変わるたびに対象ルートへ遷移する。
  useEffect(() => {
    if (index === null) return;
    const step = TOUR_STEPS[index];
    if (step?.route) navigate(step.route);
  }, [index, navigate]);

  // Esc でスキップ。
  useEffect(() => {
    if (!active) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") stop();
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") prev();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, stop, next, prev]);

  return (
    <TourContext.Provider value={{ start, available: true }}>
      {children}
      {active && (
        <TourOverlay
          index={index}
          step={TOUR_STEPS[index]}
          total={TOUR_STEPS.length}
          onNext={next}
          onPrev={prev}
          onStop={stop}
        />
      )}
    </TourContext.Provider>
  );
}

// ----------------------------------------------------------------------------

const PAD = 10; // スポットライトの余白 (px)
const CARD_W = 340;
const CARD_TOP = 88; // content カードを固定する上端 (TopNav のすぐ下)

type Rect = { top: number; left: number; width: number; height: number };

function TourOverlay({
  index,
  step,
  total,
  onNext,
  onPrev,
  onStop,
}: {
  index: number;
  step: TourStep;
  total: number;
  onNext: () => void;
  onPrev: () => void;
  onStop: () => void;
}) {
  const [rect, setRect] = useState<Rect | null>(null);
  const isLast = index >= total - 1;

  // 「タブ移動」を動的に見せる: navSelector があれば、まず移動先タブを
  // スポットライト (phase="nav") → 少し置いて selector のコンテンツへ滑らせる
  // (phase="content")。スポットライト矩形は transition で補間されるので、
  // タブ → 中身へ枠がスーッと移動して「画面が切り替わった」ことが伝わる。
  const navSel = step.navSelector;
  const [phase, setPhase] = useState<"nav" | "content">(
    navSel ? "nav" : "content",
  );
  // ステップが変わるたびに段階を初期化する (navSelector があれば nav から)。
  // nav → content は自動では進めず、クリック (advance) でのみ進む。
  useEffect(() => {
    setPhase(navSel ? "nav" : "content");
  }, [index, navSel]);

  const activeSelector = phase === "nav" ? navSel : step.selector;

  // 対象要素を (遷移直後でまだマウントされていない可能性があるので) ポーリングで
  // 探し、見つかったら中央へスクロールして矩形を採る。最大 ~2 秒で諦めて中央表示。
  useLayoutEffect(() => {
    if (!activeSelector) {
      setRect(null);
      return;
    }
    // 直前の rect は消さずに保持する。新しい矩形が採れた時点で setRect すると、
    // スポットライト枠が transition で旧位置 → 新位置へ滑らかに移動する
    // (タブ → コンテンツの「移動」を見せるための肝)。
    const selector = activeSelector;
    let raf = 0;
    let tries = 0;
    let cancelled = false;
    const measure = (el: Element) => {
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    };
    const find = () => {
      if (cancelled) return;
      const el = document.querySelector(selector);
      if (el) {
        // まず即座に採寸して遅延なくスポットライトを出す (タブ等の可視要素は
        // これで十分)。続けてスクロールし、必要なら反映後に採り直す。
        measure(el);
        el.scrollIntoView({ block: "center", behavior: "smooth" });
        window.setTimeout(() => {
          if (!cancelled) measure(el);
        }, 320);
        return;
      }
      if (tries++ < 120) raf = window.requestAnimationFrame(find);
    };
    find();
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(raf);
    };
  }, [activeSelector, index]);

  // リサイズ / スクロールで矩形を再計算する。
  useEffect(() => {
    if (!activeSelector) return;
    const selector = activeSelector;
    const update = () => {
      const el = document.querySelector(selector);
      if (el) {
        const r = el.getBoundingClientRect();
        setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
      }
    };
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [activeSelector]);

  // 実演アクション (Listen の「検索してみる」) の状態。idle → running (認識中) →
  // done (結果表示)。done になったら Next を出す。ステップが変わったら idle に戻す。
  const [actionState, setActionState] = useState<"idle" | "running" | "done">(
    "idle",
  );
  useEffect(() => {
    setActionState("idle");
  }, [index]);

  // running 中は認識結果 (Listen の「To the hunt」ボタン) の出現をポーリングし、
  // 出たら done にして Next を表示する。保険で数秒後にも done にする。
  useEffect(() => {
    if (actionState !== "running") return;
    const seen = () =>
      Array.from(document.querySelectorAll("button")).some((el) =>
        (el.textContent ?? "").includes("To the hunt"),
      );
    const id = window.setInterval(() => {
      if (seen()) setActionState("done");
    }, 200);
    const to = window.setTimeout(() => setActionState("done"), 6000);
    return () => {
      window.clearInterval(id);
      window.clearTimeout(to);
    };
  }, [actionState]);

  // 認識結果が出るとキャプション (結果 + 追加ボタン) が伸びるので、対象の矩形を
  // 測り直してスポットライトが結果まで囲うようにする。
  useEffect(() => {
    if (!activeSelector) return;
    const remeasure = () => {
      const el = document.querySelector(activeSelector);
      if (el) {
        const r = el.getBoundingClientRect();
        setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
      }
    };
    const t = window.setTimeout(remeasure, 80);
    return () => window.clearTimeout(t);
  }, [actionState, activeSelector]);

  const runAction = () => {
    if (!step.actionTarget) return;
    const el = document.querySelector(step.actionTarget);
    if (el instanceof HTMLElement) el.click();
    setActionState("running");
  };

  // このステップに未完了の実演アクションがあるか (Next を出すかの判定に使う)。
  const actionPending = Boolean(step.actionTarget) && actionState !== "done";

  // noTarget = スポットライト対象を持たないステップ (home / end)。全面ディム +
  // 画面中央カードで見せる (導入と締めを同じ見た目に揃える)。
  const noTarget = !activeSelector;
  const cardRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  // カードの実寸を測ってからビューポート内にクランプして配置する。対象が縦長で
  // 「下」に置くと画面外に出るケース (Home の 6 枚グリッド等) を防ぐ: 下に入り
  // きらなければ上、それも無理なら可視域にクランプする。useLayoutEffect なので
  // paint 前に確定し、ちらつかない。
  useLayoutEffect(() => {
    const ch = cardRef.current?.offsetHeight ?? 220;
    const cw = cardRef.current?.offsetWidth ?? CARD_W;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const clamp = (v: number, lo: number, hi: number) =>
      Math.min(Math.max(v, lo), hi);
    if (noTarget || !rect) {
      // home / end は画面中央 (cardStyle 側で処理)。測定前も pos なしにして
      // 画面外へ逃がす。
      setPos(null);
      return;
    }
    if (phase === "nav") {
      // 淡白チップは指している「タブ」の真下に置く。
      const left = clamp(
        rect.left + rect.width / 2 - cw / 2,
        12,
        Math.max(12, vw - cw - 12),
      );
      const top = clamp(
        rect.top + rect.height + PAD + 8,
        12,
        Math.max(12, vh - ch - 12),
      );
      setPos({ top, left });
    } else {
      // content / 中央 (end) のカードは上端を CARD_TOP に固定し、ステップごとに
      // カードが上下へ飛ばないよう揃える (視線を一定に保つ)。x は基本は中央だが、
      // placement="right" のときは右に寄せて中央の対象 (Listen の盤) を隠さない。
      // left / right はハイライト枠の外側に少し (GAP) 離して置く。それ以外は中央。
      const GAP = 16;
      const left =
        step.placement === "right"
          ? clamp(
              rect.left + rect.width + PAD + GAP,
              12,
              Math.max(12, vw - CARD_W - 12),
            )
          : step.placement === "left"
            ? clamp(
                rect.left - PAD - GAP - CARD_W,
                12,
                Math.max(12, vw - CARD_W - 12),
              )
            : clamp((vw - CARD_W) / 2, 12, Math.max(12, vw - CARD_W - 12));
      setPos({ top: CARD_TOP, left });
    }
  }, [rect, noTarget, phase, step.placement]);

  const cardStyle: React.CSSProperties = noTarget
    ? { top: "50%", left: "50%", transform: "translate(-50%, -50%)" }
    : pos
      ? { top: pos.top, left: pos.left }
      : { top: -9999, left: -9999 }; // 測定前は画面外に逃がす (1 フレームのみ)

  // 背景クリックで前進する。nav (タブ) 段階ならコンテンツへ、content 段階なら
  // 次ステップへ。Next ボタンと同じ進み方をどこでもできるようにする。
  const advance = () => {
    if (phase === "nav") {
      setPhase("content");
      return;
    }
    // 未完了の実演アクションがある間は、背景クリックでの読み飛ばしを止める
    // (「検索してみる」を促す)。Skip でツアー自体は抜けられる。
    if (actionPending) return;
    onNext();
  };

  return (
    <div className="fixed inset-0 z-[70]" aria-live="polite" role="dialog">
      {/* 背景レイヤ: クリックで前進。dim はスポットライトの box-shadow が担う
          ので透明。中央ステップでは下の dim div が暗転を担う。 */}
      <div className="absolute inset-0" onClick={advance} />

      {noTarget ? (
        <div className="absolute inset-0 bg-ink/55" />
      ) : rect ? (
        // スポットライト: 巨大な box-shadow で穴の外側を暗転させる。
        <div
          className="pointer-events-none absolute rounded-[4px] transition-all duration-300 ease-out"
          style={{
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            boxShadow:
              "0 0 0 9999px rgba(26,23,20,0.55), 0 0 0 2px rgba(244,239,227,0.7) inset",
          }}
        />
      ) : null}

      {phase === "nav" ? (
        // タブ移動段階: 説明は淡白に。タイトルだけの小さなチップ + 進行ヒント。
        // クリック (背景でもチップでも) でコンテンツ段階へ進む。
        <div
          ref={cardRef}
          onClick={advance}
          className="absolute cursor-pointer bg-paper px-4 py-2.5 text-left shadow-lg ring-1 ring-ink/10 transition-all duration-300 ease-out"
          style={cardStyle}
        >
          <span className="text-sm text-ink-mute">{step.title}</span>
          <span className="ml-3 text-xs italic text-ink-faint">
            Click to continue
          </span>
        </div>
      ) : (
        // コンテンツ段階: フルの吹き出しカード。
        <div
          ref={cardRef}
          onClick={(e) => e.stopPropagation()}
          className="absolute w-[340px] max-w-[calc(100vw-24px)] cursor-default bg-paper p-5 text-left text-ink shadow-xl ring-1 ring-ink/10 transition-all duration-300 ease-out"
          style={cardStyle}
        >
          <div className="mb-2 text-xs italic tabular-nums text-ink-faint">
            {index + 1} / {total}
          </div>
          <h3 className="text-base font-medium">{step.title}</h3>
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink-mute">
            {step.body}
          </p>

          <div className="mt-5 flex items-center gap-4 text-sm">
            <button
              type="button"
              onClick={onStop}
              className="mr-auto cursor-pointer italic text-ink-faint transition-colors hover:text-ink"
            >
              Skip
            </button>
            {index > 0 && (
              <button
                type="button"
                onClick={onPrev}
                className="cursor-pointer text-ink-mute transition-colors hover:text-ink"
              >
                Back
              </button>
            )}
            {step.actionTarget && actionState === "idle" ? (
              // 実演ボタン (Next の代わり)。押すと actionTarget をクリックする。
              <button
                type="button"
                onClick={runAction}
                className="cursor-pointer bg-ink px-4 py-2 text-paper transition-opacity hover:opacity-85"
              >
                {step.actionLabel ?? "Try it"}
              </button>
            ) : step.actionTarget && actionState === "running" ? (
              // 認識中は Next を出さず、進行を待たせる。
              <span className="text-xs italic text-ink-faint">Recognizing…</span>
            ) : (
              <button
                type="button"
                onClick={onNext}
                className="cursor-pointer bg-ink px-4 py-2 text-paper transition-opacity hover:opacity-85"
              >
                {isLast ? "Finish" : "Next"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
