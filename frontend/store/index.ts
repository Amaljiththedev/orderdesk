import { configureStore } from "@reduxjs/toolkit";
import { api } from "./api";
import auth from "./authSlice";

export const makeStore = () =>
  configureStore({
    reducer: { auth, [api.reducerPath]: api.reducer },
    middleware: (gdm) => gdm().concat(api.middleware),
  });

export type AppStore = ReturnType<typeof makeStore>;
export type RootState = ReturnType<AppStore["getState"]>;
export type AppDispatch = AppStore["dispatch"];
