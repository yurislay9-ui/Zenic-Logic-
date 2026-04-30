[app]
title = TITAN OMNISCALE X
package.name = titanomniscale
package.domain = org.titan
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,yaml
requirements = python3==3.11.5,fastapi,uvicorn,pydantic,fastembed,tree-sitter-languages,aiofiles,python-constraint,httpx,pyyaml,kivy,numpy
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
log_level = 2