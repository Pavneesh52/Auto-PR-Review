'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { 
  GitPullRequest, 
  ChevronDown,
  ExternalLink,
  CheckCircle,
  XCircle,
  AlertCircle,
  AlertTriangle,
  HelpCircle,
  Eye,
  FileText,
} from 'lucide-react';
import Link from 'next/link';

interface Finding {
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
}

interface ReviewDetail {
  id: string;
  repo: string;
  pr_number: number;
  pr_title: string;
  pr_body: string | null;
  diff: string;
  base_sha: string;
  head_sha: string;
  overall_confidence: number;
  outcome: string | null;
  hitl_required: boolean;
  github_review_id: number | null;
  findings: Finding[];
  created_at: string;
  updated_at: string;
}

export default function ReviewDetail() {
  const params = useParams();
  const reviewId = params.id as string;
  const [review, setReview] = useState<ReviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'findings' | 'diff' | 'trace'>('findings');

  const fetchReview = async () => {
    try {
      const res = await fetch(`/api/reviews/${reviewId}`);
      if (res.ok) {
        const data = await res.json();
        setReview(data);
      }
    } catch (error) {
      console.error('Failed to fetch review:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReview();
  }, [reviewId]);

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

  const getOutcomeBadge = (outcome: string | null, hitl: boolean) => {
    if (hitl) return (
      <span className="px-3 py-1 text-sm font-medium bg-amber-100 text-amber-800 rounded-full flex items-center gap-1">
        <AlertTriangle className="w-4 h-4" />
        HITL Required
      </span>
    );
    switch (outcome) {
      case 'approved':
        return (
          <span className="px-3 py-1 text-sm font-medium bg-green-100 text-green-800 rounded-full flex items-center gap-1">
            <CheckCircle className="w-4 h-4" />
            Approved
          </span>
        );
      case 'request_changes':
        return (
          <span className="px-3 py-1 text-sm font-medium bg-red-100 text-red-800 rounded-full flex items-center gap-1">
            <XCircle className="w-4 h-4" />
            Changes Requested
          </span>
        );
      case 'critical_block':
        return (
          <span className="px-3 py-1 text-sm font-medium bg-red-100 text-red-800 rounded-full flex items-center gap-1">
            <AlertCircle className="w-4 h-4" />
            Critical Block
          </span>
        );
      case 'escalated':
        return (
          <span className="px-3 py-1 text-sm font-medium bg-purple-100 text-purple-800 rounded-full flex items-center gap-1">
            <AlertTriangle className="w-4 h-4" />
            Escalated
          </span>
        );
      default:
        return (
          <span className="px-3 py-1 text-sm font-medium bg-gray-100 text-gray-800 rounded-full flex items-center gap-1">
            <HelpCircle className="w-4 h-4" />
            Pending
          </span>
        );
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary-500 border-t-transparent"></div>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Review Not Found</h1>
          <Link href="/" className="text-primary-600 hover:text-primary-900">Back to Dashboard</Link>
        </div>
      </div>
    );
  }

  const findingsByAgent = review.findings.reduce((acc, f) => {
    if (!acc[f.agent_type]) acc[f.agent_type] = [];
    acc[f.agent_type].push(f);
    return acc;
  }, {} as Record<string, Finding[]>);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3">
              <Link href="/" className="text-primary-600 hover:text-primary-900 flex items-center gap-1">
                <ChevronDown className="w-4 h-4" />
              </Link>
              <GitPullRequest className="w-8 h-8 text-primary-600" />
              <div>
                <h1 className="text-xl font-bold text-gray-900">{review.pr_title}</h1>
                <p className="text-sm text-gray-500">{review.repo} #{review.pr_number}</p>
              </div>
            </div>
            <nav className="flex items-center gap-4">
              <Link href="/" className="text-sm font-medium text-gray-700 hover:text-primary-600">Dashboard</Link>
              <Link href="/hitl" className="text-sm font-medium text-gray-700 hover:text-primary-600">HITL Queue</Link>
              <Link href="/economics" className="text-sm font-medium text-gray-700 hover:text-primary-600">Economics</Link>
              <Link href="/traces" className="text-sm font-medium text-gray-700 hover:text-primary-600">Traces</Link>
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
            <div className="flex items-center gap-4">
              <ExternalLink className="w-6 h-6 text-gray-400 hover:text-gray-600" title="View on GitHub" />
              <div>
                <p className="text-sm text-gray-500">Created</p>
                <p className="font-medium text-gray-900">{formatDate(review.created_at)}</p>
              </div>
              <div className="border-l border-gray-200 pl-4">
                <p className="text-sm text-gray-500">Confidence</p>
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
                  <span className="font-medium text-gray-900">
                    {(review.overall_confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
              <div className="border-l border-gray-200 pl-4">
                <p className="text-sm text-gray-500">Status</p>
                {getOutcomeBadge(review.outcome, review.hitl_required)}
              </div>
            </div>
          </div>

          <div className="border-b border-gray-200">
            <nav className="flex gap-8" aria-label="Tabs">
              {[
                { id: 'findings', label: `Findings (${review.findings.length})`, icon: AlertTriangle },
                { id: 'diff', label: 'Diff', icon: FileText },
                { id: 'trace', label: 'Trace', icon: Eye },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab.id
                      ? 'border-primary-500 text-primary-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <tab.icon className="w-4 h-4" />
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>
        </div>

        {activeTab === 'findings' && (
          <div className="space-y-6">
            {review.findings.length === 0 ? (
              <div className="bg-white rounded-lg shadow-sm border p-12 text-center">
                <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
                <h2 className="text-xl font-semibold text-gray-900 mb-2">No Issues Found</h2>
                <p className="text-gray-500">The automated review found no issues with this pull request.</p>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                  {['security', 'quality', 'tests', 'docs'].map(agent => {
                    const count = findingsByAgent[agent]?.length || 0;
                    const critical = findingsByAgent[agent]?.filter(f => f.severity === 'CRITICAL').length || 0;
                    return (
                      <div key={agent} className="bg-white rounded-lg shadow-sm border p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${getAgentColor(agent)}`}>
                            {agent}
                          </span>
                          <span className="text-sm text-gray-500">{count} findings</span>
                        </div>
                        {critical > 0 && (
                          <span className="text-sm font-medium text-red-600">{critical} critical</span>
                        )}
                      </div>
                    );
                  })}
                </div>

                <div className="space-y-4">
                  {Object.entries(findingsByAgent).map(([agent, findings]) => (
                    <div key={agent} className="bg-white rounded-lg shadow-sm border">
                      <div className="px-6 py-3 bg-gray-50 border-b flex items-center gap-2">
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${getAgentColor(agent)}`}>
                          {agent}
                        </span>
                        <h3 className="font-medium text-gray-900">{findings.length} findings</h3>
                      </div>
                      <div className="divide-y divide-gray-200">
                        {findings.map((finding) => (
                          <div key={finding.id} className="p-6 hover:bg-gray-50">
                            <div className="flex flex-wrap gap-2 mb-3">
                              <span className={`px-2 py-1 text-xs font-medium rounded-full ${getSeverityColor(finding.severity)}`}>
                                {finding.severity}
                              </span>
                              <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-800 rounded-full">
                                {finding.category}
                              </span>
                            </div>
                            <p className="text-sm font-medium text-gray-900 mb-1">{finding.summary}</p>
                            <p className="text-sm text-gray-500 mb-3 font-mono">
                              {finding.file_path}:{finding.line_start}{finding.line_end && `-${finding.line_end}`}
                            </p>
                            <div className="bg-gray-50 p-3 rounded border text-sm mb-3">
                              <p className="font-medium text-gray-900 mb-1">Suggestion:</p>
                              <p className="text-gray-700">{finding.suggestion}</p>
                            </div>
                            <div className="bg-gray-50 p-3 rounded border text-sm">
                              <p className="font-medium text-gray-900 mb-1">Rationale:</p>
                              <p className="text-gray-700">{finding.rationale}</p>
                              <p className="text-xs text-gray-500 mt-1">Confidence: {(finding.confidence * 100).toFixed(0)}%</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === 'diff' && (
          <div className="bg-white rounded-lg shadow-sm border">
            <div className="p-4 border-b bg-gray-50">
              <h2 className="text-lg font-semibold text-gray-900">Pull Request Diff</h2>
            </div>
            <div className="p-6">
              <pre className="bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto text-sm font-mono max-h-[600px] overflow-y-auto">
                {review.diff}
              </pre>
            </div>
          </div>
        )}

        {activeTab === 'trace' && (
          <div className="bg-white rounded-lg shadow-sm border">
            <div className="p-4 border-b bg-gray-50 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Execution Trace</h2>
              <Link href={`/traces`} className="text-sm font-medium text-primary-600 hover:text-primary-900">
                View Full Trace Page
              </Link>
            </div>
            <div className="p-6">
              <p className="text-gray-500 mb-4">Trace details are available on the dedicated Traces page.</p>
              <Link href={`/traces`} className="text-primary-600 hover:text-primary-900 font-medium">
                Go to Traces →
              </Link>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}