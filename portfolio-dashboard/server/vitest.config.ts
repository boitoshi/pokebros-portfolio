import { configDefaults, defineConfig } from "vitest/config";

// Vitest 4 は既定の exclude から dist を外したので、tsc の出力（dist/__tests__）まで実行してしまう。
// 3 系と同じく src のテストだけを対象にする
export default defineConfig({
  test: {
    exclude: [...configDefaults.exclude, "dist/**"],
  },
});
