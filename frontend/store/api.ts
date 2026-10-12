import { createApi, fetchBaseQuery, type BaseQueryFn, type FetchArgs, type FetchBaseQueryError } from "@reduxjs/toolkit/query/react";
import type { DocumentRow, Metrics, Order, OrderRow, ProductHit, Session, User } from "@/lib/types";
import { sessionStarted, signedOut } from "./authSlice";

type State = { auth: { token: string | null } };

const raw = fetchBaseQuery({
  baseUrl: "",
  credentials: "same-origin",
  prepareHeaders: (headers, { getState }) => {
    const token = (getState() as State).auth.token;
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return headers;
  },
});

// One refresh at a time: if five requests get 401 together, they all wait for the same refresh.
let refreshing: Promise<Session | null> | null = null;

export async function refreshSession(): Promise<Session | null> {
  refreshing ??= fetch("/auth/refresh", { method: "POST", credentials: "same-origin" })
    .then(async (r) => (r.ok ? ((await r.json()) as Session) : null))
    .catch(() => null)
    .finally(() => setTimeout(() => (refreshing = null), 0));
  return refreshing;
}

const baseQuery: BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> = async (args, api, extra) => {
  let result = await raw(args, api, extra);
  const url = typeof args === "string" ? args : args.url;
  if (result.error?.status === 401 && !url.startsWith("/auth/")) {
    const session = await refreshSession();
    if (session) {
      api.dispatch(sessionStarted(session));
      result = await raw(args, api, extra);      // retry once with the new token
    } else {
      api.dispatch(signedOut());
    }
  }
  return result;
};

export const api = createApi({
  reducerPath: "api",
  baseQuery,
  tagTypes: ["Order", "Orders", "Documents", "Users", "Metrics"],
  endpoints: (b) => ({
    login: b.mutation<Session, { email: string; password: string }>({
      query: (body) => ({ url: "/auth/login", method: "POST", body }),
    }),
    logout: b.mutation<void, void>({ query: () => ({ url: "/auth/logout", method: "POST" }) }),
    changePassword: b.mutation<Session, { current_password: string; new_password: string }>({
      query: (body) => ({ url: "/auth/change-password", method: "POST", body }),
    }),

    orders: b.query<OrderRow[], { status?: string }>({
      query: ({ status }) => ({ url: "/api/orders", params: { limit: 200, ...(status ? { status } : {}) } }),
      providesTags: ["Orders"],
    }),
    order: b.query<Order, number>({
      query: (id) => `/api/orders/${id}`,
      providesTags: (_r, _e, id) => [{ type: "Order", id }],
    }),
    fixLine: b.mutation<Order, { orderId: number; lineNo: number; version: number; product_id?: number; qty?: number }>({
      query: ({ orderId, lineNo, ...body }) => ({ url: `/api/orders/${orderId}/lines/${lineNo}`, method: "PATCH", body }),
      async onQueryStarted({ orderId }, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled;
          dispatch(api.util.upsertQueryData("order", orderId, data));   // show the saved line at once
        } catch { /* the page shows the error */ }
      },
      invalidatesTags: ["Orders"],
    }),
    approve: b.mutation<{ id: number; status: string; version: number }, { orderId: number; version: number }>({
      query: ({ orderId, version }) => ({ url: `/api/orders/${orderId}/approve`, method: "POST", body: { version } }),
      invalidatesTags: (_r, _e, a) => ["Orders", { type: "Order", id: a.orderId }],
    }),
    reject: b.mutation<{ id: number; status: string; version: number }, { orderId: number; version: number; reason: string }>({
      query: ({ orderId, ...body }) => ({ url: `/api/orders/${orderId}/reject`, method: "POST", body }),
      invalidatesTags: (_r, _e, a) => ["Orders", { type: "Order", id: a.orderId }],
    }),
    searchProducts: b.query<ProductHit[], string>({
      query: (q) => ({ url: "/api/products/search", params: { q, limit: 8 } }),
    }),

    documents: b.query<DocumentRow[], void>({ query: () => "/api/documents?limit=15", providesTags: ["Documents"] }),
    upload: b.mutation<DocumentRow, File>({
      query: (file) => {
        const body = new FormData();
        body.append("file", file);
        return { url: "/api/documents", method: "POST", body };
      },
      invalidatesTags: ["Documents", "Orders"],
    }),

    metrics: b.query<Metrics, number>({ query: (days) => `/api/metrics?days=${days}`, providesTags: ["Metrics"] }),

    users: b.query<User[], void>({ query: () => "/api/users", providesTags: ["Users"] }),
    createUser: b.mutation<User, { email: string; full_name: string; role: string; temporary_password: string }>({
      query: (body) => ({ url: "/api/users", method: "POST", body }),
      invalidatesTags: ["Users"],
    }),
    updateUser: b.mutation<User, { id: number; role?: string; is_active?: boolean; full_name?: string }>({
      query: ({ id, ...body }) => ({ url: `/api/users/${id}`, method: "PATCH", body }),
      invalidatesTags: ["Users"],
    }),
  }),
});

export const {
  useLoginMutation, useLogoutMutation, useChangePasswordMutation,
  useOrdersQuery, useOrderQuery, useFixLineMutation, useApproveMutation, useRejectMutation,
  useSearchProductsQuery, useDocumentsQuery, useUploadMutation, useMetricsQuery,
  useUsersQuery, useCreateUserMutation, useUpdateUserMutation,
} = api;
