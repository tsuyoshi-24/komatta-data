# 自動更新基盤

一度だけ:
1. GitHubに public repo `komatta-data` 作成
2. このフォルダの中身をrepo直下へアップロード
3. Settings > Pages > Source を GitHub Actions に設定
4. Actions > Update official data を1回Run
5. Pages URLを確認
6. iOS側 RemoteDataConfig.swift の REPLACE_ME URLをPages URLに変更

以後は毎週自動更新。公的サイトの仕様変更でActionが失敗した場合だけ修正します。
