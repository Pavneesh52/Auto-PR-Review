'use client';

import { useState, useEffect } from 'react';
import { 
  LayoutDashboard, 
  GitPullRequest, 
  AlertTriangle, 
  DollarSign,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  HelpCircle,
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';
import Link from 'next/link';

interface Review {
  id: string;
  repo: string;
  pr_number: number;
  pr_title: string;
  overall_confidence: number;
  outcome: string | null;
  hitl_required: boolean;
  findings_count: number;
  critical_findings: number;
  created_at: string;
}

interface Stats {
  total_reviews: number;
  pending_hitl: number;
  avg_confidence: number;
  today_cost: number;
}

export default function Dashboard() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [stats, setStats] = useState<Stats>({
    total_reviews: 0,
    pending_hitl: 0,
    avg_confidence: 0,
    today_cost: 0,
  });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  const fetchData = async () => {
    try {
      const [reviewsRes, statsRes] = await Promise.all([
        fetch('/api/reviews?page_size=50'),
        fetch('/api/economics/budget/status'),
      ]);
      
      if (reviewsRes.ok) {
        const data = await reviewsRes.json();
        setReviews(data.reviews || []);
      }
      
      if (statsRes.ok) {
        const data = await statsRes.json();
        setStats({
          total_reviews: data.total_reviews || 0,
          pending_hitl: data.pending_hitl || 0,
          avg_confidence: data.avg_confidence || 0,
          today_cost: data.today_spend_usd || 0,
        });
      }
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const filteredReviews = reviews.filter(r => {
    if (filter === 'hitl' && !r.hitl_required) return false;
    if (filter === 'critical' && r.critical_findings === 0) return false;
    if (filter === 'approved' && r.outcome !== 'approved') return false;
    if (filter === 'changes' && r.outcome !== 'request_changes') return false;
    if (searchQuery && !r.pr_title.toLowerCase().includes(searchQuery.toLowerCase()) && 
        !r.repo.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'CRITICAL': return 'bg-red-100 text-red-800';
      case 'HIGH': return 'bg-orange-100 text-orange-800';
      case 'MEDIUM': return 'bg-yellow-100 text-yellow-800';
      case 'LOW': return 'bg-blue-100 text-blue-800';
      case 'INFO': return 'bg-gray-100 text-gray-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getOutcomeBadge = (outcome: string | null, hitl: boolean) => {
    if (hitl) return (
      <span className="px-2 py-1 text-xs font-medium bg-amber-100 text-amber-800 rounded-full flex items-center gap-1">
        <AlertTriangle className="w-3 h-3" />
        HITL Required
      </span>
    );
    switch (outcome) {
      case 'approved':
        return (
          <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-full flex items-center gap-1">
            <CheckCircle className="w-3 h-3" />
            Approved
          </span>
        );
      case 'request_changes':
        return (
          <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-800 rounded-full flex items-center gap-1">
            <XCircle className="w-3 h-3" />
            Changes Requested
          </span>
        );
      case 'critical_block':
        return (
          <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-800 rounded-full flex items-center gap-1">
            <AlertCircle className="w-3 h-3" />
            Critical Block
          </span>
        );
      case 'escalated':
        return (
          <span className="px-2 py-1 text-xs font-medium bg-purple-100 text-purple-800 rounded-full flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" />
            Escalated
          </span>
        );
      default:
        return (
          <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-800 rounded-full flex items-center gap-1">
            <HelpCircle className="w-3 h-3" />
            Pending
          </span>
        );
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
              <h1 className="text-xl font-bold text-gray-900">AI PR Review Agent</h1>
            </div>
            <nav className="flex items-center gap-4">
              <Link href="/hitl" className="text-sm font-medium text-gray-700 hover:text-primary-600">
                HITL Queue
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow-sm p-6 border">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Total Reviews</p>
                <p className="text-3xl font-bold text-gray-900">{stats.total_reviews}</p>
              </div>
              <div className="p-3 bg-blue-100 rounded-full">
                <GitPullRequest className="w-6 h-6 text-blue-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm p-6 border">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Pending HITL</p>
                <p className="text-3xl font-bold text-gray-900">{stats.pending_hitl}</p>
              </div>
              <div className="p-3 bg-amber-100 rounded-full">
                <AlertTriangle className="w-6 h-6 text-amber-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm p-6 border">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Avg Confidence</p>
                <p className="text-3xl font-bold text-gray-900">{(stats.avg_confidence * 100).toFixed(1)}%</p>
              </div>
              <div className="p-3 bg-green-100 rounded-full">
                <CheckCircle className="w-6 h-6 text-green-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm p-6 border">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Today's Cost</p>
                <p className="text-3xl font-bold text-gray-900">${stats.today_cost.toFixed(2)}</p>
              </div>
              <div className="p-3 bg-purple-100 rounded-full">
                <DollarSign className="w-6 h-6 text-purple-600" />
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border">
          <div className="px-6 py-4 border-b flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <h2 className="text-lg font-semibold text-gray-900">Recent Reviews</h2>
            <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search reviews..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 w-full sm:w-64"
                />
              </div>
              <div className="relative">
                <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  className="pl-10 pr-10 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 appearance-none bg-white"
                >
                  <option value="all">All Reviews</option>
                  <option value="hitl">HITL Required</option>
                  <option value="critical">Critical Findings</option>
                  <option value="approved">Approved</option>
                  <option value="changes">Changes Requested</option>
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>
              <button
                onClick={fetchData}
                disabled={loading}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:ring-2 focus:ring-primary-500 flex items-center gap-2"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">PR</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Repository</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Confidence</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Findings</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {loading ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-gray-500">
                      <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
                      Loading reviews...
                    </td>
                  </tr>
                ) : filteredReviews.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-gray-500">
                      No reviews found
                    </td>
                  </tr>
                ) : (
                  filteredReviews.map((review) => (
                    <tr key={review.id} className="hover:bg-gray-50">
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
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-900">{review.findings_count} findings</span>
                          {review.critical_findings > 0 && (
                            <span className="px-2 py-0.5 text-xs font-medium bg-red-100 text-red-800 rounded-full">
                              {review.critical_findings} critical
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        {getOutcomeBadge(review.outcome, review.hitl_required)}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">
                        {formatDate(review.created_at)}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <Link
                            href={`/reviews/${review.id}`}
                            className="text-sm font-medium text-primary-600 hover:text-primary-900"
                          >
                            View
                          </Link>
                          <ExternalLink
                            className="w-4 h-4 text-gray-400 hover:text-gray-600"
                            title="View on GitHub"
                          />
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}