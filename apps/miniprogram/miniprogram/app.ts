import { CLOUD_ENV_ID } from "./constants/api";
import { bootstrapAuth } from "./stores/auth";

App<IAppOption>({
  globalData: {},
  onLaunch() {
    wx.cloud.init({
      env: CLOUD_ENV_ID,
      traceUser: true,
    });
    void bootstrapAuth();
  },
});
