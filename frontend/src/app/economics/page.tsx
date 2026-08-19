'use client';

import { useState, useEffect } from 'react';
import { 
  DollarSign, 
  TrendingUp, 
  TrendingDown,
  Clock,
  BarChart3,
  AlertTriangle,
  CheckCircle,
} from 'lucide-react';
import Link from 'next/link';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

interface BudgetStatus {
  daily_budget_usd: number;
  today_spend_usd: number;
  remaining_usd: number;
  percentage_used: number;
  daily_token_budget: number;
}

interface DailyCost {
  day: string;
  total_cost_usd: number;
  total_tokens: number;
  reviews_count: number;
}

interface AgentCost {
  agent: string;
  total_cost_usd: number;
  total_tokens: number;
  call_count: number;
  avg_latency_ms: number;
}

interface AgentHealth {
  bucket: string;
  agent: string;
  llm_calls: number;
  cost_usd: number;
  p95_latency_ms: number;
  rejection_rate: number;
}

const COLORS = {
  security: '#ef4444',
  quality: '#3b82f6',
  tests: '#22c55e',
  docs: '#a855f7',
  aggregator: '#6b7280',
};

export default function Economics() {
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [dailyCosts, setDailyCosts] = useState<DailyCost[]>([]);
  const [agentCosts, setAgentCosts] = useState<AgentCost[]>([]);
  const [agentHealth, setAgentHealth] = useState<AgentHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('7');

  const fetchData = async () => {
    try {
      const [budgetRes, dailyRes, agentRes, healthRes] = await Promise.all([
        fetch('/api/economics/budget/status'),
        fetch(`/api/economics/costs/daily?days=${timeRange}`),
        fetch(`/api/economics/costs/by-agent?days=${timeRange}`),
        fetch(`/api/economics/health?minutes=${timeRange === '1' ? '60' : timeRange === '7' ? '10080' : '43200'}`),
      ]);

      if (budgetRes.ok) setBudget(await budgetRes.json());
      if (dailyRes.ok) setDailyCosts((await dailyRes.json()).reverse());
      if (agentRes.ok) setAgentCosts(await agentRes.json());
      if (healthRes.ok) setAgentHealth(await healthRes.json());
    } catch (error) {
      console.error('Failed to fetch economics data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [timeRange]);

  const formatCurrency = (value: number) => `$${value.toFixed(4)}`;
  const formatNumber = (value: number) => value.toLocaleString();

  const totalCost = agentCosts.reduce((sum, a) => sum + a.total_cost_usd, 0);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3">
              <DollarSign className="w-8 h-8 text-primary-600" />
              <div>
                <h1 className="text-xl font-bold text-gray-900">Economics Dashboard</h1>
                <p className="text-sm text-gray-500">Token usage, costs, and budget tracking</p>
              </div>
            </div>
            <nav className="flex items-center gap-4">
              <Link href="/" className="text-sm font-medium text-gray-700 hover:text-primary-600">
                Dashboard
              </Link>
              <Link href="/hitl" className="text-sm font-medium text-gray-700 hover:text-primary-600">
                HITL Queue
              </Link>
              <Link href="/traces" className="text-sm font-medium text-gray-700 hover:text-primary-600">
                Traces
              </Link>
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {budget && (
          <div className="mb-8">
            <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">Daily Budget</h2>
                <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${
                  budget.percentage_used >= 100 ? 'bg-red-100 text-red-800' :
                  budget.percentage_used >= 80 ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'
                }`}>
                  {budget.percentage_used >= 100 ? <AlertTriangle className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}
                  {budget.percentage_used.toFixed(1)}% used
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <div>
                  <p className="text-sm font-medium text-gray-500">Budget</p>
                  <p className="text-3xl font-bold text-gray-900">{formatCurrency(budget.daily_budget_usd)}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-500">Spent Today</p>
                  <p className="text-3xl font-bold text-gray-900">{formatCurrency(budget.today_spend_usd)}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-500">Remaining</p>
                  <p className="text-3xl font-bold text-gray-900">{formatCurrency(budget.remaining_usd)}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-500">Token Budget</p>
                  <p className="text-3xl font-bold text-gray-900">{formatNumber(budget.daily_token_budget)}</p>
                </div>
              </div>
              <div className="mt-4 h-3 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-300 ${
                    budget.percentage_used >= 100 ? 'bg-red-500' :
                    budget.percentage_used >= 80 ? 'bg-amber-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${Math.min(budget.percentage_used, 100)}%` }}
                />
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow-sm border p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <BarChart3 className="w-5 h-5" />
              Cost by Agent ({timeRange === '1' ? 'Last 24h' : timeRange === '7' ? 'Last 7 days' : 'Last 30 days'})
            </h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={agentCosts} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tickFormatter={formatCurrency} />
                  <YAxis dataKey="agent" type="category" width={80} />
                  <Tooltip formatter={(value: number) => [formatCurrency(value), 'Cost']} />
                  <Bar dataKey="total_cost_usd" radius={[0, 4, 4, 0]}>
                    {agentCosts.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[agentCosts[index]?.agent as keyof typeof COLORS] || '#6b7280'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4">
              {agentCosts.map((agent) => (
                <div key={agent.agent} className="p-3 bg-gray-50 rounded-lg">
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: COLORS[agent.agent as keyof typeof COLORS] || '#6b7280' }}
                    />
                    <span className="font-medium capitalize">{agent.agent}</span>
                  </div>
                  <p className="text-sm text-gray-500">{formatCurrency(agent.total_cost_usd)} • {agent.call_count} calls • {agent.avg_latency_ms.toFixed(0)}ms avg</p>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm border p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <TrendingUp className="w-5 h-5" />
              Daily Cost Trend
            </h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={dailyCosts}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="day" tick={{ fontSize: 12 }} />
                  <YAxis tickFormatter={formatCurrency} />
                  <Tooltip formatter={(value: number) => [formatCurrency(value), 'Cost']} />
                  <Line
                    type="monotone"
                    dataKey="total_cost_usd"
                    stroke={COLORS.security}
                    strokeWidth={2}
                    dot={{ r: 4 }}
                    activeDot={{ r: 6 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-2xl font-bold text-gray-900">{formatCurrency(dailyCosts.reduce((sum, d) => sum + d.total_cost_usd, 0))}</p>
                <p className="text-sm text-gray-500">Total Period Cost</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{formatNumber(dailyCosts.reduce((sum, d) => sum + d.reviews_count, 0))}</p>
                <p className="text-sm text-gray-500">Total Reviews</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{formatNumber(dailyCosts.reduce((sum, d) => sum + d.total_tokens, 0))}</p>
                <p className="text-sm text-gray-500">Total Tokens</p>
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-lg shadow-sm border p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <Clock className="w-5 h-5" />
                Agent Health (Latency & Errors)
              </h2>
              <select
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
                className="px-3 py-1 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white"
              >
                <option value="1">Last Hour</option>
                <option value="7">Last 7 Days</option>
                <option value="30">Last 30 Days</option>
              </select>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={agentHealth}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
                  <YAxis tickFormatter={(value) => `${value}ms`} />
                  <Tooltip formatter={(value: number) => [`${value}ms`, 'P95 Latency']} />
                  {['security', 'quality', 'tests', 'docs', 'aggregator'].map((agent) => (
                    <Line
                      key={agent}
                      type="monotone"
                      dataKey="p95_ms"
                      stroke={COLORS[agent as keyof typeof COLORS] || '#6b7280'}
                      strokeWidth={2}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm border p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <BarChart3 className="w-5 h-5" />
              Cost Distribution by Agent
            </h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={agentCosts}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    dataKey="total_cost_usd"
                    nameKey="agent"
                    label={({ agent, total_cost_usd, percent }) => (
                      `${agent}: ${formatCurrency(total_cost_usd)} (${(percent * 100).toFixed(1)}%)`
                    )}
                    labelLine={false}
                  >
                    {agentCosts.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[agentCosts[index]?.agent as keyof typeof COLORS] || '#6b7280'} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => [formatCurrency(value), 'Cost']} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-4 flex flex-wrap gap-4">
              {agentCosts.map((agent) => (
                <div key={agent.agent} className="flex items-center gap-2">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: COLORS[agent.agent as keyof typeof COLORS] || '#6b7280' }}
                  />
                  <span className="text-sm text-gray-700">
                    {agent.agent}: {formatCurrency(agent.total_cost_usd)} ({(agent.total_cost_usd / totalCost * 100).toFixed(1)}%)
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}