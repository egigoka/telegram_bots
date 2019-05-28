#! python3
# -*- coding: utf-8 -*-
# # # bootstrap # # # 1.4.0
import sys
import os
def download_file(url, out=None):
    try:  # getting wget
        import wget
    except ModuleNotFoundError:
        os.system("pip install wget")
        import wget
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
    output_file_name = wget.download(url, out=out)
    return output_file_name

try:  # getting commands
    import commands
except (ModuleNotFoundError, ImportError):
    # getting git
    if os.system("git --version"):  # if get error while checking git version
        if sys.platform == "win32":  # getting git
            print("Downloading git, please, wait!")
            git_file_name = download_file("http://github.com/git-for-windows/git/releases/download/v2.17.1.windows.2/Git-2.17.1.2-32-bit.exe")
            print("Installing git, please, wait!")
            os.system(" ".join([git_file_name, '/VERYSILENT', '/NORESTART', '/NOCANCEL', '/SP-', '/CLOSEAPPLICATIONS',
                                '/RESTARTAPPLICATIONS', r'/COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"']))
            os.environ["PATH"] = os.environ["PATH"] + r";C:\Program Files (x86)\Git\cmd;C:\Program Files\Git\cmd"
            os.system("del " + git_file_name)
        elif sys.platform in ["linux", "linux2"]:
            os.system("sudo apt-get install git")  # todo test
        elif sys.platform == "darwin":
            os.system("brew install git")  # todo test
        else:
            raise NotImplementedError("OS " + sys.platform + " is not supported")
	# end getting git
    os.system("pip install git+https://github.com/egigoka/commands")
    import commands
# # # end bootstrap # # #