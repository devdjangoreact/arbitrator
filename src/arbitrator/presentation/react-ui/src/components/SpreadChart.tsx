import React, { useEffect, useRef } from "react";

interface Props {
  openSpreads: number[];
  closeSpreads: number[];
  shortLabel?: string;
  longLabel?: string;
  version?: number;
  height?: number;
}

const PAD_L = 42;
const PAD_R = 82;
const PAD_T = 14;
const PAD_B = 14;

function minMax(arr: number[]): [number, number] {
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < arr.length; i++) {
    const v = arr[i];
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  return [lo, hi];
}

function detectPrecision(lo: number, hi: number): number {
  let maxPrec = 2;
  for (const v of [lo, hi]) {
    if (!isFinite(v)) continue;
    const s = v.toFixed(10).replace(/0+$/, "");
    const dot = s.indexOf(".");
    if (dot === -1) continue;
    const prec = s.length - dot - 1;
    if (prec > maxPrec) maxPrec = prec;
  }
  return Math.min(maxPrec, 5);
}

export const SpreadChart: React.FC<Props> = ({
  openSpreads,
  closeSpreads,
  shortLabel = "short",
  longLabel = "long",
  version,
  height = 120,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Track canvas logical size to avoid resetting it every tick
  const sizeRef = useRef({ w: 0, h: 0, dpr: 1 });

  // Init canvas size once on mount (and on height change)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const dw = canvas.offsetWidth || 300;
    canvas.width = dw * dpr;
    canvas.height = height * dpr;
    const ctx = canvas.getContext("2d");
    if (ctx) ctx.scale(dpr, dpr);
    sizeRef.current = { w: dw, h: height, dpr };
  }, [height]);

  // Draw on every data tick — no canvas resize
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { w, h } = sizeRef.current;
    if (w === 0) return;

    const plotW = w - PAD_L - PAD_R;
    const plotH = h - PAD_T - PAD_B;

    ctx.fillStyle = "#060d1a";
    ctx.fillRect(0, 0, w, h);

    if (openSpreads.length < 2 && closeSpreads.length < 2) {
      ctx.fillStyle = "#1e3a5f";
      ctx.font = "8px monospace";
      ctx.fillText("no data", PAD_L + 4, PAD_T + plotH / 2 + 3);
      drawAxes(ctx, h, plotW, plotH);
      return;
    }

    const [oLo, oHi] = minMax(openSpreads.length ? openSpreads : [0]);
    const [cLo, cHi] = minMax(closeSpreads.length ? closeSpreads : [0]);
    const lo = Math.min(oLo, cLo);
    const hi = Math.max(oHi, cHi);
    const spread = hi - lo;
    const padY = spread * 0.12 || Math.abs(lo) * 0.05 || 0.01;
    const minY = lo - padY, maxY = hi + padY;
    const range = maxY - minY;

    const toY = (v: number) => PAD_T + plotH - ((v - minY) / range) * plotH;
    const prec = detectPrecision(minY, maxY);

    // Grid lines + Y-axis labels
    const ticks = 4;
    ctx.font = "7px monospace";
    for (let i = 0; i <= ticks; i++) {
      const frac = i / ticks;
      const v = minY + range * frac;
      const y = PAD_T + plotH * (1 - frac);
      ctx.strokeStyle = "#0f2233";
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(PAD_L, y); ctx.lineTo(PAD_L + plotW, y);
      ctx.stroke();
      ctx.fillStyle = "#ffffff";
      ctx.textAlign = "right";
      ctx.fillText(v.toFixed(prec), PAD_L - 2, y + 2);
    }
    ctx.textAlign = "left";

    // Zero line
    if (minY < 0 && maxY > 0) {
      const y0 = toY(0);
      ctx.strokeStyle = "#1e3a5f";
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 3]);
      ctx.beginPath();
      ctx.moveTo(PAD_L, y0); ctx.lineTo(PAD_L + plotW, y0);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    const drawLine = (pts: number[], color: string, endLabel: string) => {
      if (pts.length < 2) return;
      const lastIdx = pts.length - 1;
      const scaleX = plotW / lastIdx;
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.moveTo(PAD_L, toY(pts[0]));
      for (let i = 1; i <= lastIdx; i++) {
        ctx.lineTo(PAD_L + i * scaleX, toY(pts[i]));
      }
      ctx.stroke();

      const last = pts[lastIdx];
      const lx = PAD_L + lastIdx * scaleX;
      const ly = toY(last);

      ctx.beginPath();
      ctx.arc(lx, ly, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      const labelText = `${endLabel} ${last.toFixed(prec)}`;
      ctx.font = "bold 9px monospace";
      const textW = ctx.measureText(labelText).width;
      const labelX = PAD_L + plotW + 5;
      const labelY = Math.max(PAD_T + 9, Math.min(ly + 3, PAD_T + plotH + 3));
      ctx.fillStyle = "rgba(6,13,26,0.8)";
      ctx.fillRect(labelX - 1, labelY - 9, textW + 3, 11);
      ctx.fillStyle = color;
      ctx.textAlign = "left";
      ctx.fillText(labelText, labelX, labelY);
    };

    drawLine(closeSpreads, "#ef4444", "close");
    drawLine(openSpreads, "#22c55e", "open");

    ctx.font = "bold 9px monospace";
    ctx.textAlign = "left";
    ctx.fillStyle = "#22c55e";
    ctx.fillText(`↑${longLabel}`, PAD_L + 3, PAD_T + 8);
    ctx.fillStyle = "#ef4444";
    ctx.fillText(`↓${shortLabel}`, PAD_L + 3, PAD_T + 17);

    drawAxes(ctx, h, plotW, plotH);
  }, [openSpreads, closeSpreads, shortLabel, longLabel, version]);

  return (
    <canvas
      ref={canvasRef}
      width={300}
      height={height}
      style={{ width: "100%", height: `${height}px`, display: "block" }}
    />
  );
};

function drawAxes(
  ctx: CanvasRenderingContext2D,
  h: number,
  plotW: number,
  plotH: number,
) {
  ctx.strokeStyle = "#1e3a5f";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(PAD_L, PAD_T);
  ctx.lineTo(PAD_L, PAD_T + plotH);
  ctx.lineTo(PAD_L + plotW, PAD_T + plotH);
  ctx.stroke();
  ctx.fillStyle = "#1e3a5f";
  ctx.font = "7px monospace";
  ctx.fillText("←60s", PAD_L + 1, h - 2);
  ctx.textAlign = "right";
  ctx.fillText("now", PAD_L + plotW, h - 2);
  ctx.textAlign = "left";
}
