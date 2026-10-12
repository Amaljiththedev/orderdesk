import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { Session, User } from "@/lib/types";

// The access token lives only in memory (never localStorage), so a script injected into the page
// can't read it from storage. A reload restores the session from the httpOnly refresh cookie.
type Status = "unknown" | "signed_in" | "signed_out";
interface AuthState { token: string | null; user: User | null; status: Status }

const initialState: AuthState = { token: null, user: null, status: "unknown" };

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    sessionStarted(state, action: PayloadAction<Session>) {
      state.token = action.payload.access_token;
      state.user = action.payload.user;
      state.status = "signed_in";
    },
    signedOut(state) {
      state.token = null;
      state.user = null;
      state.status = "signed_out";
    },
  },
});

export const { sessionStarted, signedOut } = authSlice.actions;
export default authSlice.reducer;
