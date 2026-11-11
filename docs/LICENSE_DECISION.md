# 开源协议选择：MIT

建议程序代码与仓库内自制合成演示采用 **MIT**：篇幅短，允许使用、修改、分发和商业使用，要求保留版权和许可声明。适合希望更多个人创作者使用的小型工具。

备选 **Apache-2.0**：同为宽松协议，包含明确的专利授权和相关终止条款，对修改与 NOTICE 有额外要求。如果更看重专利条款，可选此项。

维护者已同意发布并授权选择协议，最终采用根目录的 MIT `LICENSE`，版权署名为公开 GitHub 用户名 xuyueling97-ctrl 与项目贡献者。以下保留选择依据。

## 已检查的依赖

- Streamlit 1.51.0：Apache-2.0，上游 [LICENSE](https://github.com/streamlit/streamlit/blob/1.51.0/LICENSE)。
- Pillow 12.3.0：安装包 SPDX 声明 MIT-CMU，保留安装包原文；参见 [Pillow 官方许可说明](https://pillow.readthedocs.io/en/stable/about.html#license)。
- 全部 36 个运行依赖及锁定版本见 [依赖清单](DEPENDENCIES.md)，对应许可证文本保留于 `third-party-licenses/`。
- certifi 声明 MPL-2.0，需独立保留其许可证并遵守其分发条件，不能把它重新标成 MIT。numpy 等包的 wheel 内还包含其他组件条款，包顶层元数据不替代完整附带文本。
- 本次 Windows numpy wheel 的许可文本明确列出 OpenBLAS 与 `GPL-3.0-or-later WITH GCC-exception-3.1` 运行库；pyarrow 文本包含 Apache-2.0 的 LLVM 例外条款。已保留对应全文，没有将这些组件统称为 MIT，也不在源码包中再分发这些二进制。

本候选只发布自己维护的 Python 源码、合成素材生成器、测试夹具与文档，不再分发解释器、虚拟环境或依赖 wheel。未发现此种源码发布方式必须将本项目整体置于强 copyleft 协议下的要求；这不等于对未来打包可执行文件或所有平台 wheel 作全面法律保证。以后若分发二进制，应再次核对对应平台的完整组件许可。

原作制作资料从未进入候选仓库。选定程序许可证不会自动授权《The Claude Family》的真实角色、剧本、歌曲、标识或其他作品素材。

参考：[MIT](https://choosealicense.com/licenses/mit/)、[Apache-2.0](https://choosealicense.com/licenses/apache-2.0/)。
