"use client";

import { useEffect, useState, useCallback } from "react";
import { createClient, SupabaseClient } from "@supabase/supabase-js";
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  Clock,
  TrendingUp,
  TrendingDown,
  Shield,
  Zap,
  BarChart3,
  RefreshCw,
  AlertCircle,
  Info,
  XCircle,
  ArrowUpRight,
  ArrowDownRight,
  Pause,
  Play,
  Terminal,
  DollarSign,
  Percent,
  Target,
} from "lucide-react";
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
} from "recharts";

// ============================================================================
// TYPES
// ============================================================================

interface BotState {
  symbol: string;
  is_active: boolean;
  position_type: string | null;
  entry_z: number | null;
  entry_ratio: number | null;
  current_z?: number | null;
  last_updated: string;
}

interface MarketSentiment {
  id: number;
  timestamp: string;
  risk_score: number;
  sentiment: string;
  summary: string;
}

interface TradeLog {
  id: number;
  timestamp: string;
  pair: string;
  type: string;
  side: string;
  price: number;
  z_score: number;
  pnl_percent: number;
  comment: string;
}

interface SystemLog {
  id: number;
  timestamp: string;
  level: string;
  source: string;
  message: string;
  details: string | null;
}

// ============================================================================
// SUPABASE CLIENT
// ============================================================================

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

let supabase: SupabaseClient | null = null;
if (supabaseUrl && supabaseAnonKey) {
  supabase = createClient(supabaseUrl, supabaseAnonKey);
}

// ============================================================================
// MOCK DATA (Fallback when DB is empty)
// ============================================================================

const INITIAL_TIMESTAMP = "2026-01-05T12:00:00.000Z";

const MOCK_BOT_STATES: BotState[] = [
  {
    symbol: "ATOM/DOT",
    is_active: false,
    position_type: null,
    entry_z: null,
    entry_ratio: null,
    last_updated: INITIAL_TIMESTAMP,
  },
  {
    symbol: "SAND/MANA",
    is_active: false,
    position_type: null,
    entry_z: null,
    entry_ratio: null,
    last_updated: INITIAL_TIMESTAMP,
  },
  {
    symbol: "CRV/CVX",
    is_active: false,
    position_type: null,
    entry_z: null,
    entry_ratio: null,
    last_updated: INITIAL_TIMESTAMP,
  },
];

const MOCK_SENTIMENT: MarketSentiment = {
  id: 0,
  timestamp: INITIAL_TIMESTAMP,
  risk_score: 35,
  sentiment: "SAFE",
  summary:
    "System initialized. Markets appear stable. No significant threats detected for monitored assets.",
};

const MOCK_TRADE_LOGS: TradeLog[] = [
  {
    id: 1,
    timestamp: INITIAL_TIMESTAMP,
    pair: "SYSTEM",
    type: "INIT",
    side: "NONE",
    price: 0,
    z_score: 0,
    pnl_percent: 0,
    comment: "Awaiting first signals...",
  },
];

const MOCK_SYSTEM_LOGS: SystemLog[] = [
  {
    id: 1,
    timestamp: INITIAL_TIMESTAMP,
    level: "INFO",
    source: "SYSTEM",
    message: "Dashboard initialized",
    details: null,
  },
];

// Static Z-Score history data (to avoid hydration errors)
// Generate dynamic Z-Score history (Last 24h ending at current hour LOCAL TIME)
// Process system logs to generate Z-Score history
const processZScoreHistory = (logs: SystemLog[]) => {
  const historyMap = new Map<string, any>();
  const now = new Date();

  // Initialize last 24h with nulls
  for (let i = 23; i >= 0; i--) {
    const d = new Date(now);
    d.setHours(now.getHours() - i, 0, 0, 0); // Round to hour
    const timeLabel = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
    historyMap.set(timeLabel, { time: timeLabel }); // Initialize object
  }

  // Parse logs
  // Log format: "Z-Score calculated: 0.8474 (no signal)"
  // Source: "ATOM/DOT"
  logs.forEach(log => {
    if (log.message.includes("Z-Score calculated")) {
      const match = log.message.match(/Z-Score calculated:\s*([-\d.]+)/);
      if (match) {
        const val = parseFloat(match[1]);
        const d = new Date(log.timestamp);
        // Round to nearest hour for the chart x-axis matching
        d.setMinutes(0, 0, 0);
        const bucketLabel = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });

        if (historyMap.has(bucketLabel)) {
          const entry = historyMap.get(bucketLabel);
          entry[log.source] = val;
        }
      }
    }
  });

  return Array.from(historyMap.values());
};

const STATIC_ZSCORE_HISTORY: any[] = [];

// ============================================================================
// UTILITY COMPONENTS
// ============================================================================

function LiveClock() {
  const [time, setTime] = useState<string>("--:--:--");
  const [date, setDate] = useState<string>("--- --, ----");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTime(
        now.toLocaleTimeString("en-US", {
          // timeZone: "UTC", // Removed to use local time
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })
      );
      setDate(
        now.toLocaleDateString("en-US", {
          // timeZone: "UTC", // Removed to use local time
          year: "numeric",
          month: "short",
          day: "numeric",
        })
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="text-right" suppressHydrationWarning>
      <div className="font-mono text-lg text-white" suppressHydrationWarning>{time}</div>
      <div className="text-xs text-zinc-500" suppressHydrationWarning>{date}</div>
    </div>
  );
}

function SystemStatus({ isConnected }: { isConnected: boolean }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-zinc-900 rounded-lg border border-zinc-800">
      <div className="flex items-center gap-2">
        <span className="text-zinc-500 text-xs uppercase tracking-wider">Status</span>
        <div className="relative">
          <div
            className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-emerald-500" : "bg-rose-500"
              }`}
          />
          {isConnected && (
            <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping" />
          )}
        </div>
      </div>
      <span className={`text-sm font-medium ${isConnected ? "text-emerald-400" : "text-rose-400"}`}>
        {isConnected ? "ONLINE" : "OFFLINE"}
      </span>
    </div>
  );
}

function RiskGauge({ score, sentiment }: { score: number; sentiment: string }) {
  const getColor = (s: number) => {
    if (s <= 50) return { bg: "bg-emerald-500", text: "text-emerald-500", glow: "shadow-emerald-500/30" };
    if (s <= 75) return { bg: "bg-amber-500", text: "text-amber-500", glow: "shadow-amber-500/30" };
    return { bg: "bg-rose-500", text: "text-rose-500", glow: "shadow-rose-500/30" };
  };

  const colors = getColor(score);
  const circumference = 2 * Math.PI * 45;
  const strokeDashoffset = circumference - (score / 100) * circumference * 0.75;

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-40 h-40">
        <svg className="w-full h-full -rotate-[135deg]" viewBox="0 0 100 100">
          {/* Background arc */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="#27272a"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${circumference * 0.75} ${circumference * 0.25}`}
          />
          {/* Progress arc */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            className={`${colors.text} transition-all duration-1000`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className={`text-4xl font-mono font-bold ${colors.text}`}>
            {score}
          </div>
          <div className="text-zinc-500 text-xs">/ 100</div>
        </div>
      </div>
      <div className={`mt-2 px-4 py-1.5 rounded-full text-sm font-bold ${colors.bg} bg-opacity-20 ${colors.text}`}>
        {sentiment}
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  subvalue,
  trend
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  subvalue?: string;
  trend?: "up" | "down" | "neutral";
}) {
  return (
    <div className="bg-zinc-900/50 border border-zinc-800 rounded-lg p-4">
      <div className="flex items-center gap-2 text-zinc-500 text-xs mb-2">
        <Icon className="w-4 h-4" />
        <span className="uppercase tracking-wider">{label}</span>
      </div>
      <div className="flex items-end gap-2">
        <span className="text-2xl font-mono font-bold text-white">{value}</span>
        {trend && (
          <span className={`flex items-center text-sm ${trend === "up" ? "text-emerald-400" :
            trend === "down" ? "text-rose-400" : "text-zinc-500"
            }`}>
            {trend === "up" ? <ArrowUpRight className="w-4 h-4" /> :
              trend === "down" ? <ArrowDownRight className="w-4 h-4" /> : null}
          </span>
        )}
      </div>
      {subvalue && <div className="text-xs text-zinc-500 mt-1">{subvalue}</div>}
    </div>
  );
}

function PairCard({ state, index, zScore }: { state: BotState; index: number; zScore?: number }) {
  // Map configuration by Symbol instead of Index to prevent sorting mismatches
  const config: Record<string, { name: string; icon: any; allocation: string; color: string; bgColor: string }> = {
    "ATOM/DOT": {
      name: "The Shield",
      icon: Shield,
      allocation: "40%",
      color: "text-blue-400",
      bgColor: "bg-blue-500/10"
    },
    "SAND/MANA": {
      name: "The Stability",
      icon: BarChart3,
      allocation: "35%",
      color: "text-purple-400",
      bgColor: "bg-purple-500/10"
    },
    "CRV/CVX": {
      name: "The Rocket",
      icon: Zap,
      allocation: "25%",
      color: "text-orange-400",
      bgColor: "bg-orange-500/10"
    }
  };

  const currentConfig = config[state.symbol] || {
    name: "Pair",
    icon: Activity,
    allocation: "0%",
    color: "text-indigo-400",
    bgColor: "bg-indigo-500/10"
  };

  const { name, icon: Icon, allocation, color, bgColor } = currentConfig;
  const displayZ = zScore ?? 0;
  const zColor = Math.abs(displayZ) > 2 ? "text-rose-400" :
    Math.abs(displayZ) > 1.5 ? "text-amber-400" : "text-emerald-400";

  return (
    <div className={`${bgColor} border border-zinc-800 rounded-xl p-5 hover:border-zinc-700 transition-all`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`p-2.5 bg-zinc-800/50 rounded-lg`}>
            <Icon className={`w-5 h-5 ${color}`} />
          </div>
          <div>
            <div className="font-mono font-bold text-lg text-white">
              {state.symbol}
            </div>
            <div className="text-xs text-zinc-500">{name}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-zinc-500">Allocation</div>
          <div className="font-mono font-semibold text-white">{allocation}</div>
        </div>
      </div>

      {/* Status Badge */}
      <div className="flex items-center gap-2 mb-4">
        {state.is_active ? (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/20 rounded-full">
            <div className="relative">
              <div className="w-2 h-2 rounded-full bg-emerald-500" />
              <div className="absolute inset-0 w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            </div>
            <span className="text-sm font-semibold text-emerald-400">IN POSITION</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-800 rounded-full">
            <div className="w-2 h-2 rounded-full bg-zinc-500" />
            <span className="text-sm text-zinc-400">SCANNING</span>
          </div>
        )}
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-zinc-900/50 rounded-lg px-3 py-2">
          <div className="text-zinc-500 text-xs mb-1">Z-Score</div>
          <div className={`font-mono text-xl font-bold ${zColor}`}>
            {displayZ.toFixed(2)}
          </div>
        </div>
        <div className="bg-zinc-900/50 rounded-lg px-3 py-2">
          <div className="text-zinc-500 text-xs mb-1">Side</div>
          <div className="font-mono font-semibold text-white">
            {state.is_active && state.position_type
              ? state.position_type.includes("SHORT_A") ? "S/L" : "L/S"
              : "—"}
          </div>
        </div>
      </div>

      {/* Position Details (if active) */}
      {state.is_active && (
        <div className="mt-3 pt-3 border-t border-zinc-800/50">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-zinc-500">Entry Z:</span>
              <span className="ml-2 font-mono text-white">{state.entry_z?.toFixed(2) || "—"}</span>
            </div>
            <div>
              <span className="text-zinc-500">Entry Ratio:</span>
              <span className="ml-2 font-mono text-white">{state.entry_ratio?.toFixed(4) || "—"}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TradeLogsTable({ logs }: { logs: TradeLog[] }) {
  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return {
      time: date.toLocaleTimeString("en-US", { timeZone: "UTC", hour12: false, hour: "2-digit", minute: "2-digit" }),
      date: date.toLocaleDateString("en-US", { timeZone: "UTC", month: "short", day: "numeric" }),
    };
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "ENTRY": return <ArrowUpRight className="w-4 h-4 text-emerald-400" />;
      case "EXIT": return <ArrowDownRight className="w-4 h-4 text-rose-400" />;
      default: return <Info className="w-4 h-4 text-zinc-500" />;
    }
  };

  const getTypeBadge = (type: string) => {
    switch (type) {
      case "ENTRY": return "bg-emerald-500/20 text-emerald-400 border-emerald-500/30";
      case "EXIT": return "bg-rose-500/20 text-rose-400 border-rose-500/30";
      default: return "bg-zinc-800 text-zinc-400 border-zinc-700";
    }
  };

  return (
    <div className="space-y-2">
      {logs.length === 0 ? (
        <div className="text-center text-zinc-500 py-8">
          <Activity className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No trades recorded yet</p>
        </div>
      ) : (
        logs.map((log) => {
          const { time, date } = formatTime(log.timestamp);
          return (
            <div
              key={log.id}
              className="flex items-center gap-4 p-3 bg-zinc-900/30 rounded-lg border border-zinc-800/50 hover:border-zinc-700/50 transition-colors min-w-[600px]"
            >
              {/* Icon */}
              <div className="p-2 bg-zinc-800 rounded-lg">
                {getTypeIcon(log.type)}
              </div>

              {/* Time */}
              <div className="w-20">
                <div className="font-mono text-sm text-white">{time}</div>
                <div className="text-xs text-zinc-500">{date}</div>
              </div>

              {/* Pair */}
              <div className="w-28">
                <div className="font-mono font-semibold text-white">{log.pair}</div>
                {log.side !== "NONE" && (
                  <div className="text-xs text-zinc-500">{log.side.replace(/_/g, " ")}</div>
                )}
              </div>

              {/* Type Badge */}
              <div className={`px-2.5 py-1 rounded border text-xs font-semibold ${getTypeBadge(log.type)}`}>
                {log.type}
              </div>

              {/* Z-Score */}
              <div className="w-20 text-right">
                <div className="text-xs text-zinc-500">Z-Score</div>
                <div className="font-mono text-sm text-white">{log.z_score?.toFixed(2) || "—"}</div>
              </div>

              {/* PnL */}
              <div className="w-20 text-right">
                <div className="text-xs text-zinc-500">PnL</div>
                <div className={`font-mono text-sm font-semibold ${log.pnl_percent > 0 ? "text-emerald-400" :
                  log.pnl_percent < 0 ? "text-rose-400" : "text-zinc-500"
                  }`}>
                  {log.pnl_percent !== 0 ? `${log.pnl_percent > 0 ? "+" : ""}${log.pnl_percent.toFixed(2)}%` : "—"}
                </div>
              </div>

              {/* Comment */}
              <div className="flex-1 text-xs text-zinc-500 truncate">
                {log.comment}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

function SystemLogsPanel({ logs }: { logs: SystemLog[] }) {
  const getLevelIcon = (level: string) => {
    switch (level) {
      case "ERROR": return <XCircle className="w-4 h-4 text-rose-400" />;
      case "WARNING": return <AlertTriangle className="w-4 h-4 text-amber-400" />;
      case "SUCCESS": return <CheckCircle className="w-4 h-4 text-emerald-400" />;
      default: return <Info className="w-4 h-4 text-blue-400" />;
    }
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case "ERROR": return "text-rose-400 bg-rose-500/10";
      case "WARNING": return "text-amber-400 bg-amber-500/10";
      case "SUCCESS": return "text-emerald-400 bg-emerald-500/10";
      default: return "text-blue-400 bg-blue-500/10";
    }
  };

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString("en-US", {
      // timeZone: "UTC", // Removed to use local
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  return (
    <div className="bg-zinc-950 rounded-lg p-4 font-mono text-sm max-h-64 overflow-y-auto">
      {logs.length === 0 ? (
        <div className="text-zinc-500 text-center py-4">No system logs</div>
      ) : (
        <div className="space-y-1">
          {logs.map((log) => (
            <div key={log.id} className="flex items-start gap-2 py-1 hover:bg-zinc-900/50 rounded px-2 -mx-2">
              {getLevelIcon(log.level)}
              <span className="text-zinc-500">{formatTime(log.timestamp)}</span>
              <span className={`px-1.5 py-0.5 rounded text-xs ${getLevelColor(log.level)}`}>
                {log.source}
              </span>
              <span className="text-zinc-300 flex-1">{log.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// MAIN DASHBOARD COMPONENT
// ============================================================================

export default function Dashboard() {
  const [botStates, setBotStates] = useState<BotState[]>(MOCK_BOT_STATES);
  const [sentiment, setSentiment] = useState<MarketSentiment>(MOCK_SENTIMENT);
  const [tradeLogs, setTradeLogs] = useState<TradeLog[]>(MOCK_TRADE_LOGS);
  const [systemLogs, setSystemLogs] = useState<SystemLog[]>(MOCK_SYSTEM_LOGS);
  const [zscoreHistory, setZscoreHistory] = useState<any[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<string>(INITIAL_TIMESTAMP);
  const [isLoading, setIsLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [mounted, setMounted] = useState(false);

  // Only render dynamic content after mount to avoid hydration errors
  useEffect(() => {
    setMounted(true);
  }, []);

  // Calculate statistics
  const totalTrades = tradeLogs.filter(l => l.type === "ENTRY" || l.type === "EXIT").length;
  const totalPnL = tradeLogs.reduce((acc, l) => acc + (l.pnl_percent || 0), 0);
  const activePositions = botStates.filter(s => s.is_active).length;
  const winRate = tradeLogs.filter(l => l.type === "EXIT" && l.pnl_percent > 0).length /
    Math.max(1, tradeLogs.filter(l => l.type === "EXIT").length) * 100;

  // Extract Z-scores from system logs (fallback when current_z column doesn't exist)
  const extractZScoresFromLogs = (logs: SystemLog[]): Record<string, number> => {
    const zScores: Record<string, number> = {};
    const pairNames = ["ATOM/DOT", "SAND/MANA", "CRV/CVX"];

    for (const pair of pairNames) {
      const log = logs.find(l => l.source === pair && l.message.includes("Z-Score calculated"));
      if (log) {
        const match = log.message.match(/Z-Score calculated:\s*([-\d.]+)/);
        if (match) {
          zScores[pair] = parseFloat(match[1]);
        }
      }
    }
    return zScores;
  };

  const zScoresFromLogs = extractZScoresFromLogs(systemLogs);

  // Fetch data from Supabase
  const fetchData = useCallback(async () => {
    if (!supabase) {
      console.warn("Supabase not configured. Using mock data.");
      return;
    }

    setIsLoading(true);

    try {
      // Fetch bot states
      const { data: states, error: statesError } = await supabase
        .from("bot_state")
        .select("*")
        .order("symbol");

      if (!statesError && states && states.length > 0) {
        setBotStates(states);
      }

      // Fetch latest sentiment
      const { data: sentimentData, error: sentimentError } = await supabase
        .from("market_sentiment")
        .select("*")
        .order("timestamp", { ascending: false })
        .limit(1);

      if (!sentimentError && sentimentData && sentimentData.length > 0) {
        setSentiment(sentimentData[0]);
      }

      // Fetch ALL trade logs (not just 5)
      const { data: logs, error: logsError } = await supabase
        .from("trade_logs")
        .select("*")
        .order("timestamp", { ascending: false })
        .limit(50);

      if (!logsError && logs && logs.length > 0) {
        setTradeLogs(logs);
      }

      // Fetch system logs (if table exists)
      try {
        const { data: sysLogs, error: sysLogsError } = await supabase
          .from("system_logs")
          .select("*")
          .order("timestamp", { ascending: false })
          .limit(200); // Increased limit for graph history

        if (!sysLogsError && sysLogs && sysLogs.length > 0) {
          setSystemLogs(sysLogs);
          setZscoreHistory(processZScoreHistory(sysLogs));
        }
      } catch {
        // Table might not exist yet
      }

      setIsConnected(true);
      setLastRefresh(new Date().toISOString());
    } catch (error) {
      console.error("Failed to fetch data:", error);
      setIsConnected(false);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch and auto-refresh
  useEffect(() => {
    fetchData();
    if (autoRefresh) {
      const interval = setInterval(fetchData, 15000); // Refresh every 15s
      return () => clearInterval(interval);
    }
  }, [fetchData, autoRefresh]);

  const isTradingHalted = sentiment.risk_score > 75;

  return (
    <div className="min-h-screen bg-black text-white">
      {/* ================================================================== */}
      {/* HEADER */}
      {/* ================================================================== */}
      <header className="border-b border-zinc-800 px-6 py-4 sticky top-0 bg-black/95 backdrop-blur z-50">
        <div className="max-w-[1600px] mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="p-2.5 bg-gradient-to-br from-indigo-600 to-purple-600 rounded-xl">
              <Activity className="w-6 h-6" />
            </div>
            <div>
              <h1 className="font-mono font-bold text-xl tracking-tight flex items-center gap-2">
                QUANTUM SNIPER
                <span className="px-2 py-0.5 bg-indigo-500/20 text-indigo-400 text-xs rounded-full border border-indigo-500/30">
                  SIMULATION
                </span>
              </h1>
              <p className="text-xs text-zinc-500">Pairs Trading Bot • Mean Reversion Strategy</p>
            </div>
          </div>

          <div className="flex flex-wrap justify-center items-center gap-4">
            {/* Auto-refresh toggle */}
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${autoRefresh
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-zinc-900 border-zinc-800 text-zinc-500"
                }`}
            >
              {autoRefresh ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
              <span className="text-sm">Auto</span>
            </button>

            {/* Manual refresh */}
            <button
              onClick={fetchData}
              disabled={isLoading}
              className="flex items-center gap-2 px-3 py-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-lg transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
              <span className="text-sm">Refresh</span>
            </button>

            <SystemStatus isConnected={isConnected} />
            <LiveClock />
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto p-6 space-y-6">
        {/* Trading Halted Banner */}
        {isTradingHalted && (
          <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl flex items-center gap-4">
            <AlertTriangle className="w-6 h-6 text-rose-400" />
            <div>
              <div className="font-semibold text-rose-400">TRADING HALTED</div>
              <div className="text-sm text-rose-400/70">Risk score exceeds 75%. All trading operations suspended.</div>
            </div>
          </div>
        )}

        {/* ================================================================ */}
        {/* TOP STATS ROW */}
        {/* ================================================================ */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon={Target}
            label="Active Positions"
            value={activePositions}
            subvalue={`of ${botStates.length} pairs`}
          />
          <StatCard
            icon={Activity}
            label="Total Trades"
            value={totalTrades}
            subvalue="entries + exits"
          />
          <StatCard
            icon={Percent}
            label="Win Rate"
            value={`${winRate.toFixed(0)}%`}
            trend={winRate >= 50 ? "up" : "down"}
          />
          <StatCard
            icon={DollarSign}
            label="Total PnL"
            value={`${totalPnL >= 0 ? "+" : ""}${totalPnL.toFixed(2)}%`}
            trend={totalPnL >= 0 ? "up" : "down"}
          />
        </div>

        {/* ================================================================ */}
        {/* RISK & PORTFOLIO ROW */}
        {/* ================================================================ */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Risk Module */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6">
            <div className="flex items-center gap-2 mb-6">
              <AlertCircle className={`w-5 h-5 ${sentiment.risk_score <= 50 ? "text-emerald-500" :
                sentiment.risk_score <= 75 ? "text-amber-500" : "text-rose-500"
                }`} />
              <h2 className="font-semibold text-zinc-300">Risk Level</h2>
            </div>
            <RiskGauge score={sentiment.risk_score} sentiment={sentiment.sentiment} />
            <div className="mt-4 text-center text-xs text-zinc-500">
              Updated {new Date(sentiment.timestamp).toLocaleString("en-US", { timeZone: "UTC" })}
            </div>
          </div>

          {/* Portfolio Cards */}
          <div className="lg:col-span-3 grid grid-cols-1 md:grid-cols-3 gap-4">
            {botStates.map((state, index) => (
              <PairCard
                key={state.symbol}
                state={state}
                index={index}
                zScore={zScoresFromLogs[state.symbol] ?? state.current_z}
              />
            ))}
          </div>
        </div>

        {/* ================================================================ */}
        {/* AI SUMMARY */}
        {/* ================================================================ */}
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <Terminal className="w-5 h-5 text-indigo-400" />
            <h2 className="font-semibold text-zinc-300">AI Market Analysis</h2>
          </div>
          <div className="bg-zinc-950 rounded-lg p-4 font-mono text-sm">
            <div className="text-emerald-400 mb-2">$ gemini --analyze --risk-assessment</div>
            <div className="text-zinc-300 leading-relaxed whitespace-pre-wrap">{sentiment.summary}</div>
          </div>
        </div>

        {/* ================================================================ */}
        {/* CHARTS & LOGS ROW */}
        {/* ================================================================ */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Z-Score Chart */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-indigo-400" />
                <h2 className="font-semibold text-zinc-300">Z-Score History (24H)</h2>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1">
                  <div className="w-3 h-0.5 bg-blue-400 rounded" />
                  <span className="text-zinc-500">ATOM/DOT</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-3 h-0.5 bg-purple-400 rounded" />
                  <span className="text-zinc-500">SAND/MANA</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-3 h-0.5 bg-orange-400 rounded" />
                  <span className="text-zinc-500">CRV/CVX</span>
                </div>
              </div>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={zscoreHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis
                    dataKey="time"
                    stroke="#52525b"
                    tick={{ fill: "#71717a", fontSize: 10 }}
                    tickLine={false}
                  />
                  <YAxis
                    stroke="#52525b"
                    tick={{ fill: "#71717a", fontSize: 10 }}
                    tickLine={false}
                    domain={[-3, 3]}
                    ticks={[-2, -1, 0, 1, 2]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#18181b",
                      border: "1px solid #27272a",
                      borderRadius: "8px",
                      fontSize: "12px",
                    }}
                    labelStyle={{ color: "#a1a1aa" }}
                  />
                  {/* Entry threshold lines */}
                  <Line type="monotone" dataKey={() => 2} stroke="#f43f5e" strokeDasharray="5 5" dot={false} />
                  <Line type="monotone" dataKey={() => -2} stroke="#f43f5e" strokeDasharray="5 5" dot={false} />
                  <Line type="monotone" dataKey={() => 0} stroke="#52525b" strokeDasharray="3 3" dot={false} />
                  {/* Z-Score lines */}
                  {/* Z-Score lines - Matching PairCard colors */}
                  <Line type="monotone" dataKey="ATOM/DOT" stroke="#3b82f6" strokeWidth={2} dot={false} />  {/* Blue-500 */}
                  <Line type="monotone" dataKey="SAND/MANA" stroke="#a855f7" strokeWidth={2} dot={false} /> {/* Purple-500 */}
                  <Line type="monotone" dataKey="CRV/CVX" stroke="#f97316" strokeWidth={2} dot={false} />   {/* Orange-500 */}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="text-center text-xs text-zinc-600 mt-2">
              Entry threshold: ±2.0 (red dashed lines)
            </div>
          </div>

          {/* System Logs */}
          <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6">
            <div className="flex items-center gap-2 mb-4">
              <Terminal className="w-5 h-5 text-indigo-400" />
              <h2 className="font-semibold text-zinc-300">System Logs</h2>
            </div>
            <SystemLogsPanel logs={systemLogs} />
          </div>
        </div>

        {/* ================================================================ */}
        {/* TRADE HISTORY */}
        {/* ================================================================ */}
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-indigo-400" />
              <h2 className="font-semibold text-zinc-300">Trade History</h2>
              <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded">
                {tradeLogs.length} records
              </span>
            </div>
          </div>
          <div className="overflow-x-auto">
            <TradeLogsTable logs={tradeLogs.slice(0, 20)} />
          </div>
        </div>

        {/* ================================================================ */}
        {/* FOOTER */}
        {/* ================================================================ */}
        <footer className="text-center text-zinc-600 text-xs py-4 border-t border-zinc-800">
          <div className="font-mono flex flex-col md:flex-row items-center justify-center gap-2 md:gap-4">
            <span>QUANTUM SNIPER v1.0</span>
            <span>•</span>
            <span>Simulation Mode</span>
            <span>•</span>
            <span>Last refresh: {mounted ? new Date(lastRefresh).toLocaleTimeString("en-US", { timeZone: "UTC" }) : "--:--:--"} UTC</span>
            <span>•</span>
            <span className={isConnected ? "text-emerald-500" : "text-rose-500"}>
              {isConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
}
