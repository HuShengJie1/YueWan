import { CLOUD_CONTAINER_SERVICE } from "../constants/api";

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T | null;
}

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";
type RequestData = Record<string, unknown> | string | ArrayBuffer;

export interface RequestOptions {
  path: string;
  method?: HttpMethod;
  data?: RequestData;
  headers?: Record<string, string>;
  authenticated?: boolean;
  responseMode?: "json" | "no-content";
}

interface RequestAuthConfiguration {
  getAccessToken: () => string | null;
  onUnauthorized: () => void;
}

let authConfiguration: RequestAuthConfiguration = {
  getAccessToken: () => null,
  onUnauthorized: () => undefined,
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly statusCode: number,
    readonly code?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function configureRequestAuth(configuration: RequestAuthConfiguration): void {
  authConfiguration = configuration;
}

function buildHeaders(options: RequestOptions): Record<string, string> {
  const accessToken = options.authenticated === false ? null : authConfiguration.getAccessToken();

  return {
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    ...options.headers,
  };
}

function isApiResponse(value: unknown): value is ApiResponse<unknown> {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const response = value as Partial<ApiResponse<unknown>>;
  return (
    typeof response.code === "number" &&
    typeof response.message === "string" &&
    Object.prototype.hasOwnProperty.call(response, "data")
  );
}

function parseResponse<T>(
  body: unknown,
  statusCode: number,
  authenticated: boolean,
  responseMode: "json" | "no-content" = "json",
): T {
  const response = isApiResponse(body) ? body : null;

  if (statusCode === 204) {
    if (responseMode === "no-content") {
      return undefined as T;
    }

    throw new ApiError("服务响应缺少数据", statusCode);
  }

  if (statusCode >= 200 && statusCode < 300) {
    if (responseMode === "no-content") {
      throw new ApiError("服务响应状态异常", statusCode);
    }

    if (!response) {
      throw new ApiError("服务响应格式异常", statusCode);
    }

    if (response.code !== 0) {
      throw new ApiError(response.message, statusCode, response.code);
    }

    if (response.data === null) {
      throw new ApiError("服务响应缺少数据", statusCode);
    }

    return response.data as T;
  }

  if (statusCode === 401 && authenticated) {
    authConfiguration.onUnauthorized();
  }

  throw new ApiError(
    response?.message ?? `Request failed with HTTP ${statusCode}`,
    statusCode,
    response?.code,
  );
}

export function request<T>(options: RequestOptions): Promise<T> {
  return new Promise((resolve, reject) => {
    wx.cloud.callContainer({
      path: options.path,
      service: CLOUD_CONTAINER_SERVICE,
      method: options.method ?? "GET",
      data: options.data,
      header: {
        ...buildHeaders(options),
        "X-WX-SERVICE": CLOUD_CONTAINER_SERVICE,
      },
      dataType: "json",
      success: (response) => {
        try {
          resolve(
            parseResponse<T>(
              response.data,
              response.statusCode,
              options.authenticated !== false,
              options.responseMode,
            ),
          );
        } catch (error) {
          reject(error);
        }
      },
      fail: (error) => {
        reject(new ApiError(error.errMsg, 0));
      },
    });
  });
}
