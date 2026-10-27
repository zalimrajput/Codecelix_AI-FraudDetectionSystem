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
  TransactionStatus
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
  // Use backend-calculated risk score if available, otherwise use status-based defaults
  const riskScore = backendRiskScore !== undefined ? backendRiskScore : (s === 'blocked' || s === 'block' ? 88 : s === 'review' ? 52 : 12);
  return { status: (s === 'blocked' || s === 'block' ? 'FAILED' : s === 'review' ? 'PENDING' : 'COMPLETED'), decision, riskLevel, riskScore };
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

  if (filter?.page) queryParams.page = filter.page;
  if (filter?.limit) queryParams.page_size = filter.limit;
  if (filter?.search) queryParams.search = filter.search;
  if (filter?.minAmount) queryParams.min_amount = filter.minAmount;
  if (filter?.maxAmount) queryParams.max_amount = filter.maxAmount;
  if (filter?.startDate) queryParams.date_from = filter.startDate;
  if (filter?.endDate) queryParams.date_to = filter.endDate;
  if (filter?.status && filter.status !== 'ALL') queryParams.status = filter.status;
  if (filter?.riskLevel && filter.riskLevel !== 'ALL') queryParams.riskLevel = filter.riskLevel;

  const data = await apiClient<{ items: BackendTransaction[]; total: number }>('/transactions', {
    method: 'GET',
    params: queryParams,
  });

  const rawItems = Array.isArray(data.items) ? data.items : [];
  return {
    transactions: rawItems.map(formatTransaction),
    total: data.total ?? rawItems.length,
  };
}

export async function getTransactionById(id: string): Promise<Transaction> {
  const data = await apiClient<BackendTransaction>(`/transactions/${id}`, {
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

  const res = await apiClient<BackendTransaction>('/transactions/manual', {
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
