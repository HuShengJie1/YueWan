import { bootstrapAuth } from "./stores/auth";

App<IAppOption>({
  globalData: {},
  onLaunch() {
    void bootstrapAuth();
  },
});
