import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, LineSeries, LineStyle, Time } from 'lightweight-charts';
import type { IndicatorPoint } from '@/hooks/use-trading-api';

interface RSIPaneProps {
  rsiData: IndicatorPoint[] | undefined;
}

export function RSIPane({ rsiData }: RSIPaneProps) {
  const [expanded, setExpanded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  const latest = rsiData && rsiData.length > 0 ? rsiData[rsiData.length - 1].value : null;

  useEffect(() => {
    if (!expanded || !containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#94a3b8', fontSize: 10, fontFamily: "'Roboto Mono', monospace" },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { visible: true, borderVisible: false },
      timeScale: { visible: false, borderVisible: false },
      handleScroll: false,
      handleScale: false,
    });

    const series = chart.addSeries(LineSeries, {
      color: '#a78bfa', lineWidth: 2, lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: false, lastValueVisible: true, priceLineVisible: false,
      autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }),
    });

    series.createPriceLine({ price: 70, color: 'rgba(239,83,80,0.5)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '' });
    series.createPriceLine({ price: 50, color: 'rgba(148,163,184,0.4)', lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: '' });
    series.createPriceLine({ price: 30, color: 'rgba(38,166,154,0.5)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '' });

    if (rsiData && rsiData.length > 0) {
      series.setData(rsiData.map(p => ({ time: p.time as Time, value: p.value })) as any);
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;
    seriesRef.current = series;

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [expanded]);

  useEffect(() => {
    if (!expanded || !seriesRef.current || !rsiData) return;
    try {
      seriesRef.current.setData(rsiData.map(p => ({ time: p.time as Time, value: p.value })) as any);
    } catch {}
  }, [rsiData, expanded]);

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        title="Expand RSI pane"
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'rgba(167,139,250,0.12)', border: '1px solid rgba(167,139,250,0.35)',
          borderRadius: 999, padding: '3px 10px', cursor: 'pointer',
          fontFamily: "'Roboto Mono', monospace", fontSize: 11,
        }}
      >
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', display: 'inline-block' }} />
        <span style={{ color: '#c4b5fd' }}>RSI {latest !== null ? latest.toFixed(1) : '—'}</span>
      </button>
    );
  }

  return (
    <div style={{ background: '#080b12', borderTop: '1px solid #1e2637', height: 96, position: 'relative' }}>
      <button
        onClick={() => setExpanded(false)}
        title="Collapse RSI pane"
        style={{
          position: 'absolute', top: 4, left: 8, zIndex: 2,
          background: 'transparent', border: 'none', cursor: 'pointer',
          color: '#c4b5fd', fontFamily: "'Roboto Mono', monospace", fontSize: 10,
        }}
      >
        RSI 14 · {latest !== null ? latest.toFixed(1) : '—'}
      </button>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
    </div>
  );
}