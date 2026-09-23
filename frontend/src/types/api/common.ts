export type ApiErrorResponse = {
  status?: string;
  message?: string;
  request_id?: string;
  error_code?: string;
  error_message?: string;
  detail?: unknown;
  [key: string]: unknown;
};

export type ApiResponse<T> = {
  status?: string;
  message?: string;
  request_id?: string;
  data?: T;
  [key: string]: unknown;
};

export type PaginatedResponse<T> = {
  items?: T[];
  rows?: T[];
  page?: number;
  pageSize?: number;
  total?: number;
  totalPages?: number;
  [key: string]: unknown;
};
