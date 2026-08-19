'use client';

import { useState, useEffect } from 'react';
import { 
  GitPullRequest, 
  Search,
  Filter,
  ChevronDown,
  Eye,
  Clock,
  Zap,
  Brain,
  Terminal,
  AlertTriangle,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import Link from 'next/link';

interface TraceEvent {
  ts: string;
  agent: string;
  event_type: string;
  model: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  latency_ms: number | null;
  outcome: string | null;
  confidence: number | null;
}

interface Trace {
  review: {
    id: string;
    repo: string;
    pr_number: number;
    pr_title: string;
    overall_confidence: number;
    outcome: string | null;
    hitl_required: boolean;
    created_at: string;
  };
  findings: Array<{
    id: string;
    agent_type: string;
    severity: string;
    category: string;
    summary: string;
    file_path: string;
    line_start: number;
    line_end: number | null;
    suggestion: string;
    confidence: number;
    rationale: string;
  }>;
  trace: TraceEvent[];
}

export default function Traces() {
  const [traces, setTraces] = useState<Array<{
    review_id: string;
    repo: string;
    pr_number: number;
    pr_title: string;
    overall_confidence: number;
    outcome: string | null;
    hitl_required: boolean;
    created_at: string;
  }>>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTrace, setSelectedTrace] = useState<Trace | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [agentFilter, setAgentFilter] = useState('all');

  const fetchTraces = async () => {
    try {
      const res = await fetch('/api/reviews?page_size=50');
      if (res.ok) {
        const data = await res.json();
        setTraces(data.reviews || []);
      }
    } catch (error) {
      console.error('Failed to fetch traces:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchTraceDetail = async (reviewId: string) => {
    try {
      const res = await fetch(`/api/reviews/${reviewId}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedTrace(data);
      }
    } catch (error) {
      console.error('Failed to fetch trace detail:', error);
    }
  };

  useEffect(() => {
    fetchTraces();
  }, []);

  const filteredTraces = traces.filter(t => {
    if (searchQuery && !t.pr_title.toLowerCase().includes(searchQuery.toLowerCase()) && 
        !t.repo.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  const getEventIcon = (eventType: string) => {
    switch (eventType) {
      case 'span.start': return <Zap className="w-4 h-4 text-blue-500" />;
      case 'span.end': return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'llm.call': return <Brain className="w-4 h-4 text-purple-500" />;
      case 'tool.call': return <Terminal className="w-4 h-4 text-orange-500" />;
      case 'decision': return <AlertTriangle className="w-4 h-4 text-red-500" />;
      case 'escalation': return <XCircle className="w-4 h-4 text-red-500" />;
      default: return <Clock className="w-4 h-4 text-gray-500" />;
    }
  };

  const getAgentColor = (agent: string) => {
    switch (agent) {
      case 'security': return 'bg-red-100 text-red-800';
      case 'quality': return 'bg-blue-100 text-blue-800';
      case 'tests': return <span className="bg-green-100 text-green-800">tests</span>;
      case 'docs': return 'bg-purple-100 text-purple-800';
      case 'aggregator': return 'bg-gray-100 text-gray-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  if (selectedTrace) {
    return (
      <div className="min-h-screen bg-gray-50">
        <header className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center h-16">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setSelectedTrace(null)}
                  className="text-sm font-medium text-primary-600 hover:text-primary-900 flex items-center gap-1"
                >
                  <ChevronDown className="w-4 h-4" />
                  Back to Traces
                </button>
                <GitPullRequest className="w-8 h-8 text-primary-600" />
                <div>
                  <h1 className="text-xl font-bold text-gray-900">Trace Detail</h1>
                  <p className="text-sm text-gray-500">{selectedTrace.review.repo} #{selectedTrace.review.pr_number}</p>
                </div>
              </div>
              <nav className="flex items-center gap-4">
                <Link href="/" className="text-sm font-medium text-gray-700 hover:text-primary-600">Dashboard</Link>
                <Link href="/hitl" className="text-sm font-medium text-gray-700 hover:text-primary-600">HITL Queue</Link>
                <Link href="/economics" className="text-sm font-medium text-gray-700 hover:text-primary-600">Economics</Link>
              </nav>
            </div>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <div className="bg-white rounded-lg shadow-sm border p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Event Timeline</h2>
                <div className="space-y-4">
                  {selectedTrace.trace.map((event, index) => (
                    <div key={`${event.ts}-${index}`} className="flex gap-4 pb-4 border-b last:border-0">
                      <div className="flex-shrink-0 w-10 text-center">
                        <div className="w-2 h-2 rounded-full bg-primary-500 mt-2" />
                        {index < selectedTrace.trace.length - 1 && (
                          <div className="w-0.5 h-full bg-gray-200 ml-1" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3">
                          {getEventIcon(event.event_type)}
                          <div>
                            <p className="font-medium text-gray-900">{event.event_type}</p>
                            <p className="text-sm text-gray-500">{event.agent} • {formatDate(event.ts)}</p>
                          </div>
                          {event.model && (
                            <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded">{event.model}</span>
                          )}
                          {event.latency_ms && (
                            <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded">{event.latency_ms}ms</span>
                          )}
                          {event.cost_usd && (
                            <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded">${event.cost_usd.toFixed(6)}</span>
                          )}
                          {event.tokens_in && event.tokens_out && (
                            <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded">
                              {event.tokens_in}+{event.tokens_out} tokens
                            </span>
                          )}
                          {event.confidence && (
                            <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded">
                              Conf: {(event.confidence * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                        {event.payload && (
                          <pre className="mt-2 text-xs bg-gray-50 p-2 rounded overflow-x-auto max-h-32">
                            {JSON.stringify(event.payload, null, 2)}
                          </pre>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {selectedTrace.findings.length > 0 && (
                <div className="bg-white rounded-lg shadow-sm border p-6">
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">Findings ({selectedTrace.findings.length})</h2>
                  <div className="space-y-4">
                    {selectedTrace.findings.map((finding) => (
                      <div key={finding.id} className="border rounded-lg p-4 bg-gray-50">
                        <div className="flex flex-wrap gap-2 mb-3">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                            finding.severity === 'CRITICAL' ? 'bg-red-100 text-red-800' :
                            finding.severity === 'HIGH' ? 'bg-orange-100 text-orange-800' :
                            finding.severity === 'MEDIUM' ? 'bg-yellow-100 text-yellow-800' :
                            finding.severity === 'LOW' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'
                          }`}>
                            {finding.severity}
                          </span>
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                            finding.agent_type === 'security' ? 'bg-red-100 text-red-800' :
                            finding.agent_type === 'quality' ? 'bg-blue-100 text-blue-800' :
                            finding.agent_type === 'tests' ? 'bg-green-100 text-green-800' : 'bg-purple-100 text-purple-800'
                          }`}>
                            {finding.agent_type}
                          </span>
                          <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-800 rounded-full">
                            {finding.category}
                          </span>
                        </div>
                        <p className="text-sm font-medium text-gray-900 mb-1">{finding.summary}</p>
                        <p className="text-sm text-gray-500 mb-2 font-mono">
                          {finding.file_path}:{finding.line_start}{finding.line_end && `-${finding.line_end}`}
                        </p>
                        <div className="bg-white p-3 rounded border text-sm">
                          <p className="font-medium text-gray-900 mb-1">Suggestion:</p>
                          <p className="text-gray-700">{finding.suggestion}</p>
                        </div>
                        <div className="mt-2 bg-white p-3 rounded border text-sm">
                          <p className="font-medium text-gray-900 mb-1">Rationale:</p>
                          <p className="text-gray-700">{finding.rationale}</p>
                          <p className="text-xs text-gray-500 mt-1">Confidence: {(finding.confidence * 100).toFixed(0)}%</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow-sm border p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Review Summary</h2>
                <div className="space-y-3">
                  <div>
                    <p className="text-sm text-gray-500">Repository</p>
                    <p className="font-medium text-gray-900 font-mono">{selectedTrace.review.repo}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">PR</p>
                    <p className="font-medium text-gray-900">#{selectedTrace.review.pr_number} - {selectedTrace.review.pr_title}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Overall Confidence</p>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            selectedTrace.review.overall_confidence >= 0.8 ? 'bg-green-500' :
                            selectedTrace.review.overall_confidence >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                          }`}
                          style={{ width: `${selectedTrace.review.overall_confidence * 100}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-gray-700">
                        {(selectedTrace.review.overall_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Outcome</p>
                    <span className={`px-3 py-1 text-sm font-medium rounded-full ${
                      selectedTrace.review.hitl_required ? 'bg-amber-100 text-amber-800' :
                      selectedTrace.review.outcome === 'approved' ? 'bg-green-100 text-green-800' :
                      selectedTrace.review.outcome === 'request_changes' ? 'bg-red-100 text-red-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {selectedTrace.review.hitl_required ? 'HITL Required' : selectedTrace.review.outcome || 'Pending'}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Started</p>
                    <p className="font-medium text-gray-900">{new Date(selectedTrace.review.created_at).toLocaleString()}</p>
                  </div>
                </div>
              </div>

              <div className="bg-white rounded-lg shadow-sm border p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Event Stats</h2>
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-gray-50 p-3 rounded">
                      <p className="text-xs text-gray-500">Total Events</p>
                      <p className="text-2xl font-bold text-gray-900">{selectedTrace.trace.length}</p>
                    </div>
                    <div className="bg-gray-50 p-3 rounded">
                      <p className="text-xs text-gray-500">LLM Calls</p>
                      <p className="text-2xl font-bold text-gray-900">
                        {selectedTrace.trace.filter(e => e.event_type === 'llm.call').length}
                      </p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-gray-50 p-3 rounded">
                      <p className="text-xs text-gray-500">Total Cost</p>
                      <p className="text-2xl font-bold text-gray-900">
                        ${selectedTrace.trace.reduce((sum, e) => sum + (e.cost_usd || 0), 0).toFixed(6)}
                      </p>
                    </div>
                    <div className="bg-gray-50 p-3 rounded">
                      <p className="text-xs text-gray-500">Total Tokens</p>
                      <p className="text-2xl font-bold text-gray-900">
                        {selectedTrace.trace.reduce((sum, e) => sum + (e.tokens_in || 0) + (e.tokens_out || 0), 0).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500 mb-2">By Agent</p>
                    <div className="space-y-1">
                      {['security', 'quality', 'tests', 'docs', 'aggregator'].map(agent => {
                        const count = selectedTrace.trace.filter(e => e.agent === agent).length;
                        if (count === 0) return null;
                        return (
                          <div key={agent} className="flex items-center justify-between text-sm">
                            <span className={`px-2 py-0.5 rounded-full ${getAgentColor(agent)}`}>{agent}</span>
                            <span className="font-medium text-gray-900">{count} events</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3">
              <GitPullRequest className="w-8 h-8 text-primary-600" />
              <h1 className="text-xl font-bold text-gray-900">Execution Traces</h1>
            </div>
            <nav className="flex items-center gap-4">
              <Link href="/" className="text-sm font-medium text-gray-700 hover:text-primary-600">Dashboard</Link>
              <Link href="/hitl" className="text-sm font-medium text-gray-700 hover:text-primary-600">HITL Queue</Link>
              <Link href="/economics" className="text-sm font-medium text-gray-700 hover:text-primary-600">Economics</Link>
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <h2 className="text-lg font-semibold text-gray-900">Recent Executions ({traces.length})</h2>
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search traces..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 w-full"
            />
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Review</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Repository</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Confidence</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Started</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-500">Loading...</td>
                </tr>
              ) : filteredTraces.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-500">No traces found</td>
                </tr>
              ) : (
                filteredTraces.map((trace) => (
                  <tr key={trace.review_id} className="hover:bg-gray-50 cursor-pointer" onClick={() => fetchTraceDetail(trace.review_id)}>
                    <td className="px-6 py-4">
                      <div>
                        <p className="text-sm font-medium text-gray-900 truncate max-w-xs">
                          {trace.pr_title}
                        </p>
                        <p className="text-sm text-gray-500">#{trace.pr_number}</p>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <p className="text-sm text-gray-900 font-mono">{trace.repo}</p>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              trace.overall_confidence >= 0.8 ? 'bg-green-500' :
                              trace.overall_confidence >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                            }`}
                            style={{ width: `${trace.overall_confidence * 100}%` }}
                          />
                        </div>
                        <span className="text-sm font-medium text-gray-700">
                          {(trace.overall_confidence * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                        trace.hitl_required ? 'bg-amber-100 text-amber-800' :
                        trace.outcome === 'approved' ? 'bg-green-100 text-green-800' :
                        trace.outcome === 'request_changes' ? 'bg-red-100 text-red-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {trace.hitl_required ? 'HITL Required' : trace.outcome || 'Pending'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {new Date(trace.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4">
                      <button
                        onClick={(e) => { e.stopPropagation(); fetchTraceDetail(trace.review_id); }}
                        className="text-sm font-medium text-primary-600 hover:text-primary-900 flex items-center gap-1"
                      >
                        <Eye className="w-4 h-4" />
                        View Trace
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}