import { md5 } from "js-md5";
import { sha256Hex } from "@/utils/sha256";

export interface DashboardPasswordHashes {
  sha256: string;
  md5: string;
}

export async function hashDashboardPassword(
  password: string,
): Promise<DashboardPasswordHashes> {
  if (!password) {
    return { sha256: "", md5: "" };
  }

  return { sha256: await sha256Hex(password), md5: md5(password) };
}
