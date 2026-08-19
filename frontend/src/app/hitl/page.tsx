'use client';

import { useState, useEffect } from 'react';
import { 
  GitPullRequest, 
  AlertTriangle, 
  CheckCircle,
  XCircle,
  AlertCircle,
  ChevronDown,
  ExternalLink,
  Eye,
  FileText,
} from 'lucide-react';
import Link from 'next/link';

interface HITLReview {
  hitl_id: string;
  review_id: string;
  repo: string;
  pr_number: number;
  pr_title: string;
  status: string;
  overall_confidence: number;
  created_at: string;
}

interface HITLDetail {
  hitl: {
    id: string;
    review_id: string;
    status: string;
    reviewer_id: string | null;
    decision: string | null;
    feedback: string | null;
    created_at: string;
  };
  review: {
    id: string;
    repo: string;
    pr_number: number;
    pr_title: string;
    overall_confidence: number;
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
}

export default function HITLQueue() {
  const [queue, setQueue] = useState<HITLReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedReview, setSelectedReview] = useState<HITLDetail | null>(null);
  const [filter, setFilter] = useState('all');

  const fetchQueue = async () => {
    try {
      const res = await fetch('/api/hitl/queue?limit=50');
      if (res.ok) {
        const data = await res.json();
        setQueue(data);
      }
    } catch (error) {
      console.error('Failed to fetch queue:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchDetail = async (hitlId: string) => {
    try {
      const res = await fetch(`/api/hitl/${hitlId}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedReview(data);
      }
    } catch (error) {
      console.error('Failed to fetch detail:', error);
    }
  };

  const handleDecision = async (hitlId: string, decision: 'approved' | 'request_changes') => {
    try {
      const res = await fetch(`/api/hitl/${hitlId}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, reviewer_id: 'current_user' }),
      });
      if (res.ok) {
        fetchQueue();
        setSelectedReview(null);
      }
    } catch (error) {
      console.error('Failed to submit decision:', error);
    }
  };

  useEffect(() => {
    fetchQueue();
    const interval = setInterval(fetchQueue, 15000);
    return () => clearInterval(interval);
  }, []);

  const filteredQueue = queue.filter(r => {
    if (filter === 'pending' && r.status !== 'pending') return false;
    if (filter === 'escalated' && r.status !== 'escalated') return false;
    return true;
  });

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'CRITICAL': return 'bg-red-100 text-red-800 border-red-200';
      case 'HIGH': return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'MEDIUM': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'LOW': return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'INFO': return 'bg-gray-100 text-gray-800 border-gray-200';
      default: return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  const getAgentColor = (agent: string) => {
    switch (agent) {
      case 'security': return 'bg-red-100 text-red-800';
      case 'quality': return 'bg-blue-100 text-blue-800';
      case 'tests': return 'bg-green-100 text-green-800';
      case 'docs': return 'bg-purple-100 text-purple-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3">
              <GitPullRequest className="w-8 h-8 text-primary-600" />
              <div>
                <h1 className="text-xl font-bold text-gray-900">HITL Review Queue</h1>
                <p className="text-sm text-gray-500">Human-in-the-loop review for escalated PRs</p>
              </div>
            </div>
            <nav className="flex items-center gap-4">
              <Link href="/" className="text-sm font-medium text-gray-700 hover:text-primary-600">
                Dashboard
              </Link>
              <Link href="/economics" className="text-sm font-medium text-gray-700 hover:text-primary-600">
                Economics
              </Link>
              <Link href="/traces" className="text-sm font-medium text-gray-700 hover:text-primary-600">
                Traces
              </Link>
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {selectedReview ? (
          <div className="mb-6">
            <button
              onClick={() => setSelectedReview(null)}
              className="text-sm font-medium text-primary-600 hover:text-primary-900 flex items-center gap-1 mb-4"
            >
              <ChevronDown className="w-4 h-4" />
              Back to Queue
            </button>
            
            <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
              <div className="px-6 py-4 border-b bg-gray-50">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900">{selectedReview.review.pr_title}</h2>
                    <p className="text-sm text-gray-500">{selectedReview.review.repo} #{selectedReview.review.pr_number}</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-500">Confidence:</span>
                      <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            selectedReview.review.overall_confidence >= 0.8 ? 'bg-green-500' :
                            selectedReview.review.overall_confidence >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                          }`}
                          style={{ width: `${selectedReview.review.overall_confidence * 100}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-gray-700">
                        {(selectedReview.review.overall_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {selectedReview.hitl.feedback && (
                <div className="px-6 py-4 border-b bg-amber-50">
                  <p className="text-sm font-medium text-amber-800">Escalation Reason:</p>
                  <p className="text-sm text-amber-700 mt-1">{selectedReview.hitl.feedback}</p>
                </div>
              )}

              <div className="p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Findings ({selectedReview.findings.length})</h3>
                {selectedReview.findings.length === 0 ? (
                  <p className="text-gray-500 text-center py-8">No findings</p>
                ) : (
                  <div className="space-y-4">
                    {selectedReview.findings.map((finding) => (
                      <div key={finding.id} className="border rounded-lg p-4 bg-gray-50">
                        <div className="flex flex-wrap gap-2 mb-3">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${getSeverityColor(finding.severity)}`}>
                            {finding.severity}
                          </span>
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${getAgentColor(finding.agent_type)}`}>
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
                )}

                <div className="mt-6 flex gap-4">
                  <button
                    onClick={() => handleDecision(selectedReview.hitl.id, 'approved')}
                    className="px-6 py-2 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 focus:ring-2 focus:ring-green-500 focus:ring-offset-2"
                  >
                    <CheckCircle className="w-4 h-4 inline mr-2" />
                    Approve
                  </button>
                  <button
                    onClick={() => handleDecision(selectedReview.hitl.id, 'request_changes')}
                    className="px-6 py-2 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
                  >
                    <XCircle className="w-4 h-4 inline mr-2" />
                    Request Changes
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <h2 className="text-lg font-semibold text-gray-900">Pending Reviews ({filteredQueue.length})</h2>
              <div className="flex gap-2">
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 bg-white"
                >
                  <option value="all">All</option>
                  <option value="pending">Pending</option>
                  <option value="escalated">Escalated</option>
                </select>
              </div>
            </div>

            <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">PR</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Repository</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Confidence</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Waiting Since</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {loading ? (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center text-gray-500">Loading...</td>
                    </tr>
                  ) : filteredQueue.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center text-gray-500">No pending reviews</td>
                    </tr>
                  ) : (
                    filteredQueue.map((review) => (
                      <tr key={review.hitl_id} className="hover:bg-gray-50 cursor-pointer" onClick={() => fetchDetail(review.hitl_id)}>
                        <td className="px-6 py-4">
                          <div>
                            <p className="text-sm font-medium text-gray-900 truncate max-w-xs">
                              {review.pr_title}
                            </p>
                            <p className="text-sm text-gray-500">#{review.pr_number}</p>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <p className="text-sm text-gray-900 font-mono">{review.repo}</p>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2">
                            <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  review.overall_confidence >= 0.8 ? 'bg-green-500' :
                                  review.overall_confidence >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                                }`}
                                style={{ width: `${review.overall_confidence * 100}%` }}
                              />
                            </div>
                            <span className="text-sm font-medium text-gray-700">
                              {(review.overall_confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                            review.status === 'escalated' ? 'bg-red-100 text-red-800' : 'bg-amber-100 text-amber-800'
                          }`}>
                            {review.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-500">
                          {formatDate(review.created_at)}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={(e) => { e.stopPropagation(); fetchDetail(review.hitl_id); }}
                              className="text-sm font-medium text-primary-600 hover:text-primary-900 flex items-center gap-1"
                            >
                              <Eye className="w-4 h-4" />
                              Review
                            </button>
                            <ExternalLink className="w-4 h-4 text-gray-400 hover:text-gray-600" title="View on GitHub" />
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </main>
    </div>
  );
}