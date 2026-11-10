import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatMetric } from "../lib/format";

export const CHART_COLORS = ["#22d3ee", "#3b82f6", "#34d399", "#fbbf24", "#f87171", "#a78bfa"];

const axisStyle = { fill: "#5b7088", fontSize: 10 };
const tooltipStyle = {
  background: "#07111d",
  border: "1px solid #1b3049",
  borderRadius: 8,
  fontSize: 11,
  color: "#e6eef8",
  boxShadow: "0 12px 30px -18px #000",
};
const gridStyle = { stroke: "#15283d", strokeDasharray: "3 4" };

export function ScoreHistogram({ data, series, height = 240 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 8, left: -22, bottom: 0 }}>
        <CartesianGrid {...gridStyle} vertical={false} />
        <XAxis dataKey="bin" tick={axisStyle} tickLine={false} axisLine={{ stroke: "#1b3049" }} interval={3} />
        <YAxis tick={axisStyle} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(34,211,238,0.04)" }} />
        <Legend wrapperStyle={{ fontSize: 10, color: "#8094ab" }} />
        {series.map((item) => (
          <Bar key={item.key} dataKey={item.key} name={item.name} fill={item.color} radius={[2, 2, 0, 0]} opacity={0.85} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function CurveChart({
  series,
  xKey = "fpr",
  yKey = "tpr",
  xLabel = "False-positive rate",
  yLabel = "True-positive rate",
  height = 250,
  diagonal = true,
}) {
  const hasPoints = series.some((item) => item.points?.length);
  if (!hasPoints) {
    return <div className="flex h-[240px] items-center justify-center text-[11px] text-slate-600">Curve unavailable for this experiment.</div>;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 8, right: 14, left: -14, bottom: 4 }}>
        <CartesianGrid {...gridStyle} />
        <XAxis
          type="number"
          dataKey={xKey}
          name={xLabel}
          domain={[0, 1]}
          tick={axisStyle}
          tickLine={false}
          axisLine={{ stroke: "#1b3049" }}
          label={{ value: xLabel, position: "insideBottom", offset: -2, fill: "#5b7088", fontSize: 9 }}
        />
        <YAxis
          type="number"
          dataKey={yKey}
          name={yLabel}
          domain={[0, 1]}
          tick={axisStyle}
          tickLine={false}
          axisLine={false}
          label={{ value: yLabel, angle: -90, position: "insideLeft", fill: "#5b7088", fontSize: 9 }}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(value) => formatMetric(value, 3)}
          cursor={{ strokeDasharray: "3 3", stroke: "#334155" }}
        />
        <Legend wrapperStyle={{ fontSize: 10, color: "#8094ab" }} />
        {diagonal && (
          <Scatter
            name="Chance"
            data={[{ [xKey]: 0, [yKey]: 0 }, { [xKey]: 1, [yKey]: 1 }]}
            fill="#334155"
            line={{ stroke: "#334155", strokeDasharray: "4 4", strokeWidth: 1 }}
            shape={() => null}
            legendType="none"
          />
        )}
        {series.filter((item) => item.points?.length).map((item, index) => (
          <Scatter
            key={item.name}
            name={item.name}
            data={item.points}
            fill={item.color || CHART_COLORS[index % CHART_COLORS.length]}
            line={{ stroke: item.color || CHART_COLORS[index % CHART_COLORS.length], strokeWidth: 1.8 }}
            shape="circle"
          />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export function MetricComparison({ rows, metrics, height = 270 }) {
  if (!rows?.length) {
    return <div className="flex h-[240px] items-center justify-center text-[11px] text-slate-600">Run experiments to compare models.</div>;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
        <CartesianGrid {...gridStyle} vertical={false} />
        <XAxis dataKey="label" tick={{ ...axisStyle, fontSize: 9 }} tickLine={false} axisLine={{ stroke: "#1b3049" }} interval={0} />
        <YAxis domain={[0, 1]} tick={axisStyle} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value) => formatMetric(value, 3)} cursor={{ fill: "rgba(34,211,238,0.04)" }} />
        <Legend wrapperStyle={{ fontSize: 10, color: "#8094ab" }} />
        {metrics.map((metric, index) => (
          <Bar
            key={metric.key}
            dataKey={metric.key}
            name={metric.label}
            fill={CHART_COLORS[index % CHART_COLORS.length]}
            radius={[2, 2, 0, 0]}
            opacity={0.85}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function FeatureImportance({ items, height = 250 }) {
  if (!items?.length) {
    return <div className="flex h-[180px] items-center justify-center text-[11px] text-slate-600">Feature importance is unavailable for this model.</div>;
  }
  const data = items.slice(0, 10).map((item) => ({
    name: String(item.feature).replace(/^(num|cat)__/, ""),
    value: item.importance,
  }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 18, left: 16, bottom: 0 }}>
        <CartesianGrid {...gridStyle} horizontal={false} />
        <XAxis type="number" tick={axisStyle} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="name" width={118} tick={{ ...axisStyle, fontSize: 9 }} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value) => formatMetric(value, 4)} cursor={{ fill: "rgba(34,211,238,0.04)" }} />
        <Bar dataKey="value" fill="#22d3ee" radius={[0, 3, 3, 0]} opacity={0.8} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function CompositionChart({ data, height = 210 }) {
  const total = data.reduce((sum, item) => sum + (Number(item.value) || 0), 0);
  if (!total) {
    return <div className="flex h-[180px] items-center justify-center text-[11px] text-slate-600">No test predictions available.</div>;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={48} outerRadius={74} paddingAngle={2} stroke="#07111d">
          {data.map((item) => (
            <Cell key={item.name} fill={item.color} />
          ))}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 10, color: "#8094ab" }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function MiniArea({ data, dataKey, color = "#22d3ee", height = 90 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 5, right: 4, left: 4, bottom: 0 }}>
        <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.6} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function TimelineBars({ points, height = 220 }) {
  if (!points?.length) return <div className="flex h-[160px] items-center justify-center text-[11px] text-slate-600">No score timeline available.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={points} margin={{ top: 6, right: 8, left: -24, bottom: 0 }}>
        <CartesianGrid {...gridStyle} vertical={false} />
        <XAxis dataKey="index" tick={axisStyle} tickLine={false} axisLine={{ stroke: "#1b3049" }} />
        <YAxis domain={[0, 1]} tick={axisStyle} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={tooltipStyle} formatter={(value) => formatMetric(value, 3)} />
        <Line type="monotone" dataKey="score" stroke="#f87171" strokeWidth={1.2} dot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="benign" stroke="#34d399" strokeWidth={1.2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
