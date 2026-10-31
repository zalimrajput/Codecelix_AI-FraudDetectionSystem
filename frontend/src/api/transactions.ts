/**
 * CodeCelix Transactions Service
 *
 * Integrated with FastAPI backend:
 * - GET  /api/transactions
 * - GET  /api/transactions/{id}
 * - POST /api/transactions/manual
 * - POST /api/transactions/import/csv
 */

import { apiClient } from './client';
import {
  Transaction,
  TransactionFilter,
  ManualTransactionPayload,
  CsvImportResult,
  PaymentMethod,
  RiskLevel,
  TransactionDecision,
  TransactionStatus,
} from '../types/transaction';

interface BackendTransaction {
  id: string;
  txn_external_id?: string;
  customer_id: string;
  amount: number;
  currency?: string;
  payment_method?: string;
  status?: string;
  device_id?: string;
  ip_address_str?: string;
  country?: string;
  city?: string;
  created_at: string;
  reviewed?: boolean;
  risk_score?: number;
}

interface BackendTransactionDetail extends BackendTransaction {
  decision?: string;
  risk_level?: string;
  risk_score?: number;
}

function mapPaymentMethod(pm?: string): PaymentMethod {
  const p = (pm || '').toLowerCase();
  if (p.includes('credit')) return 'CREDIT_CARD';
  if (p.includes('debit')) return 'DEBIT_CARD';
  if (p.includes('crypto')) return 'CRYPTO';
  if (p.includes('transfer') || p.includes('wire')) return 'WIRE_TRANSFER';
  if (p.includes('wallet') || p.includes('paypal') || p.includes('upi')) return 'DIGITAL_WALLET';
  return 'CREDIT_CARD';
}

function mapStatus(status?: string, backendRiskScore?: number): { status: TransactionStatus; decision: TransactionDecision; riskLevel: RiskLevel; riskScore: number } {
  // Keep Transaction.status aligned with the backend decision value the filter sends,
  // so the status dropdown and the status column speak the same language.
  const s = (status || '').toLowerCase();
  let riskLevel: RiskLevel;
  let decision: TransactionDecision;
  if (s === 'blocked' || s === 'block') {
    riskLevel = 'HIGH';
    decision = 'BLOCKED';
  } else if (s === 'review') {
    riskLevel = 'MEDIUM';
    decision = 'REVIEW';
  } else {
    riskLevel = 'LOW';
    decision = 'APPROVED';
  }
  // Keep the real backend decision stored on Transaction.status, not a UI-only label.
  const mappedStatus: TransactionStatus =
    s === 'blocked' || s === 'block' ? 'BLOCKED' : s === 'review' ? 'REVIEW' : 'APPROVED';
  const riskScore = backendRiskScore !== undefined ? backendRiskScore : (s === 'blocked' || s === 'block' ? 88 : s === 'review' ? 52 : 12);
  return { status: mappedStatus, decision, riskLevel, riskScore };
}

function formatTransaction(t: BackendTransaction): Transaction {
  // Pass the backend-calculated riskScore if available, fallback to status-based mapping
  const backendRiskScore = t.risk_score !== undefined ? t.risk_score : undefined;
  const { status, decision, riskLevel, riskScore } = mapStatus(t.status, backendRiskScore);
  const locationParts = [t.city, t.country].filter(Boolean);

  return {
    id: t.id,
    customerId: t.customer_id,
    customerName: t.customer_id,
    amount: Number(t.amount || 0),
    currency: t.currency || 'USD',
    paymentMethod: mapPaymentMethod(t.payment_method),
    ipAddress: t.ip_address_str || '127.0.0.1',
    deviceId: t.device_id || 'unknown-device',
    location: locationParts.length > 0 ? locationParts.join(', ') : 'Global',
    riskScore,
    riskLevel,
    decision,
    status,
    timestamp: t.created_at || new Date().toISOString(),
    flags: [],
  };
}

export async function getTransactions(filter?: TransactionFilter): Promise<{ transactions: Transaction[]; total: number }> {
  const queryParams: Record<string, string | number | boolean | undefined> = {};

  // Always request the backend's max page: without an explicit limit the API
  // defaults to page_size=20, which truncated the table below the dashboard
  // total (page_size is capped at 100 by the API).
  queryParams.page = filter?.page ?? 1;
  queryParams.page_size = filter?.limit ?? 100;
  if (filter?.search) queryParams.search = filter.search;
  if (filter?.minAmount) queryParams.min_amount = filter.minAmount;
  if (filter?.maxAmount) queryParams.max_amount = filter.maxAmount;

  if (filter?.startDate) queryParams.date_from = filter.startDate;
  if (filter?.endDate) queryParams.date_to = filter.endDate;
  if (filter?.status && filter.status !== 'ALL') queryParams.status = filter.status;
  if (filter?.riskLevel && filter.riskLevel !== 'ALL') queryParams.risk_level = filter.riskLevel;

  // NOTE: backend list_transactions filters by `risk_level` (snake_case). This param name
  // must match what backend expects so the combined status + risk_level filter works.

  const data = await apiClient<{ items: BackendTransaction[]; total: number }>('/transactions', {
    method: 'GET',
    params: queryParams,
  });

  const rawItems = Array.isArray(data.items) ? data.items : [];
  // Never surface transactions without a backend risk score: they are unscored
  // rows left over from before the decision engine ran (risk_score is NULL).
  const scoredItems = rawItems.filter((t) => t.risk_score != null);
  const removedCount = rawItems.length - scoredItems.length;
  return {
    transactions: scoredItems.map(formatTransaction),
    total: (data.total ?? rawItems.length) - removedCount,
  };
}

export async function getTransactionById(id: string): Promise<Transaction> {
  const data = await apiClient<BackendTransactionDetail>(`/transactions/${id}`, {
    method: 'GET',
  });
  return formatTransaction(data);
}

export async function createTransaction(data: ManualTransactionPayload): Promise<Transaction> {
  const payload: Record<string, unknown> = {
    customer_id: data.customerId,
    amount: data.amount,
    currency: data.currency || 'USD',
    payment_method: data.paymentMethod?.toLowerCase() || 'card',
    ip_address: data.ipAddress || undefined,
    device_id: data.deviceId || undefined,
    country: data.country || undefined,
    city: data.city || undefined,
    device_info: data.deviceType || undefined,
  };

  // Optional risk-signal feature overrides (consumed by the decision engine / ML pipeline)
  if (data.deviceType) payload.device_type = data.deviceType;
  if (data.deviceAgeDays !== undefined) payload.device_age_days = data.deviceAgeDays;
  if (data.isNewDevice !== undefined) payload.is_new_device = data.isNewDevice;
  if (data.accountAgeDays !== undefined) payload.account_age_days = data.accountAgeDays;
  if (data.customerAvgAmount !== undefined) payload.customer_avg_amount = data.customerAvgAmount;
  if (data.distanceFromHomeKm !== undefined) payload.distance_from_home_km = data.distanceFromHomeKm;
  if (data.ipAccountCount !== undefined) payload.ip_account_count = data.ipAccountCount;
  if (data.sharedIp !== undefined) payload.shared_ip = data.sharedIp;
  if (data.sharedDevice !== undefined) payload.shared_device = data.sharedDevice;
  if (data.deviceCustomerCount !== undefined) payload.device_customer_count = data.deviceCustomerCount;

  const res = await apiClient<BackendTransactionDetail>('/transactions/manual', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  return formatTransaction(res);
}

export async function importTransactionsCsv(file: File): Promise<CsvImportResult> {
  const formData = new FormData();
  formData.append('file', file);

  const token = localStorage.getItem('codecelix_auth_token');
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api';

  const response = await fetch(`${baseUrl}/transactions/import/csv`, {
    method: 'POST',
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
  });

  if (!response.ok) {
    let errorMessage = `Upload failed with status ${response.status}`;
    try {
      const err = await response.json();
      errorMessage = err.detail || err.message || errorMessage;
    } catch {
      // Non-JSON response
    }
    throw new Error(errorMessage);
  }

  const result = await response.json();
  const created = result.created || 0;
  const errors = result.errors || [];

  return {
    totalProcessed: created + errors.length,
    successful: created,
    failed: errors.length,
    flaggedHighRisk: 0,
    errors: errors.map((e: any) => ({ row: e.line || 0, reason: e.error || 'Validation error' })),
  };
}
