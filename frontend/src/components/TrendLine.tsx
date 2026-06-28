"use client";

// Line chart of a single metric across seasons (spec §6.2): the season-over-
// season evolution of e.g. points per game for a player.

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface TrendPoint {
  label: string;
  value: number;
}

/**
 * Render a labelled trend line for a metric over time.
 *
 * @param points - Ordered data points (e.g. one per season).
 * @param metricLabel - Human-readable name of the plotted metric.
 * @param color - Stroke colour (defaults to orange-red).
 * @param compact - When true, renders a small sparkline without visible axes.
 */
export function TrendLine({
  points,
  metricLabel,
  color = "#c0612b",
  compact = false,
}: {
  points: TrendPoint[];
  metricLabel: string;
  color?: string;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <ResponsiveContainer width="100%" height={80}>
        <LineChart data={points} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <Line
            type="monotone"
            dataKey="value"
            name={metricLabel}
            stroke={color}
            strokeWidth={2}
            dot={points.length <= 6}
          />
          <Tooltip
            formatter={(v: number) => [v.toFixed(1), metricLabel]}
            labelStyle={{ fontSize: 10 }}
            contentStyle={{ fontSize: 11 }}
          />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={points}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="label" />
        <YAxis />
        <Tooltip />
        <Line
          type="monotone"
          dataKey="value"
          name={metricLabel}
          stroke={color}
          strokeWidth={2}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
