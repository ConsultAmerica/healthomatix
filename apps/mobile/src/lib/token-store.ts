import * as SecureStore from "expo-secure-store";

const ACCESS_TOKEN_KEY = "healthomatix.access-token";

export function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
}

export function storeAccessToken(token: string): Promise<void> {
  if (!token.trim()) {
    throw new Error("An access token must not be empty.");
  }
  return SecureStore.setItemAsync(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken(): Promise<void> {
  return SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
}
