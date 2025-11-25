import shutil
import sys
import subprocess
import threading
import queue
import os
from dataclasses import dataclass
import argparse

@dataclass
class cfg_mujoco_c:
    src_dir:str
    build_dir:str
    install_dir:str
    build_type:str
    cmake_extra_flag:str


@dataclass
class config:
    mujoco_c:cfg_mujoco_c



class cmd_shell:
    def __init__(self ):

        git_bash_key = 'GIT_BASH'
        if git_bash_key in os.environ:
            bash_path = os.environ[git_bash_key]
        elif sys.platform == "win32":
            print(f'please set environment variable {git_bash_key}:')
            print(f'On Windows: your_git/bin/bash.exe')
            exit(1)
        else:
            unix_bash_path='/usr/bin/bash'
            if os.path.exists(unix_bash_path):
                bash_path='/usr/bin/bash'
            else:
                print(f'please set environment variable {git_bash_key}:')
                print(f'On Linux: /usr/bin/bash')
                exit(1)

        self.process = subprocess.Popen(
            [bash_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            #shell=True,
            bufsize=1,
            env=os.environ,
            universal_newlines = True,  # Use the default encoding (UTF-8) on modern Python versions
            encoding = 'utf-8'  # Explicitly specify UTF-8 encoding
        )

        # two queues: one for stdout, one for stderr
        self.stdout_q = queue.Queue()
        self.stderr_q = queue.Queue()

        # reader threads
        threading.Thread(target=self._reader, args=(self.process.stdout, self.stdout_q), daemon=True).start()
        threading.Thread(target=self._reader, args=(self.process.stderr, self.stderr_q), daemon=True).start()


    def run(self, *cmd):
        command = " ".join(list(cmd))

        """Send a command and return stdout + stderr output."""

        self.process.stdin.write(_echo_cmd(command)+ "\n")
        self.process.stdin.flush()

        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()

        self.process.stdin.write(_return_code_cmd()+ "\n")
        self.process.stdin.flush()

        self.process.stdin.write(_end_cmd()+ "\n")
        self.process.stdin.flush()

        stdout_lines = []
        stderr_lines = []


        while True:
            something_wrong = False
            try:
                line = self.stdout_q.get_nowait()
                stdout_lines.append(line)
            except queue.Empty:
                pass

            try:
                line = self.stderr_q.get_nowait()
                stderr_lines.append(line)
                something_wrong = True
            except queue.Empty:
                pass

            if _check_output_complete(stdout_lines):
                break  # No more output for now


        out=''.join(stdout_lines)
        print(out.strip())

        if len(stderr_lines)>0:
            err=''.join(stderr_lines)
            print(err)
            ret_code=_get_return_code(stdout_lines)
            if ret_code != 0:
                exit(ret_code)


    def _reader(self, pipe, q):
        for line in pipe:
            q.put(line)

    def close(self):
        self.process.terminate()


end_str='----'

def _check_cmd_begins(lines):
    return len(lines) > 0 and  lines[-1].strip() == end_str

def _check_output_complete(lines):
    return len(lines)>0 and  lines[0][0]=='$' and  lines[-1].strip() == end_str

def _get_return_code(lines):
    return int(lines[-2].strip())

def _echo_cmd(cmd):
    return 'echo $ '+ cmd

def _end_cmd():
    return 'echo '+ end_str

def _return_code_cmd():
    return 'echo $?'

def __copytree(dst, src, symlinks = False, ignore = None):
    for item in os.listdir(src):
        s = _join_path(src, item)
        d = _join_path(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)

def _create_virtual_env_if_not_exists(dir,cmd):
    if not os.path.exists(dir):
        cmd.run('python', '-m', 'venv', dir)

    if sys.platform == "win32":
        f = dir + '/Scripts/activate'
    else:
        f = dir + '/bin/activate'
    cmd.run('source', f)


def _cmake_install_mujoco_c(cfg_mujoco_c, cmd):


    src_flag='-S'+ cfg_mujoco_c.src_dir
    build_dir_flag='-B'+ cfg_mujoco_c.build_dir

    install_dir_flag = _cmake_kv('CMAKE_INSTALL_PREFIX', cfg_mujoco_c.install_dir)

    if not os.path.exists(cfg_mujoco_c.build_dir):
        os.mkdir(cfg_mujoco_c.build_dir)
    cmd.run('cmake', src_flag , build_dir_flag, install_dir_flag, cfg_mujoco_c.cmake_extra_flag)

    cmd.run('rm', cfg_mujoco_c.install_dir + '/*','-rf')
    cmd.run('cmake', '--build' ,cfg_mujoco_c.build_dir, '--target', 'install' , '--config', cfg_mujoco_c.build_type, )

    MUJOCO_PATH = os.environ['MUJOCO_PATH']
    MUJOCO_PLUGIN_PATH = os.environ['MUJOCO_PLUGIN_PATH']
    MUJOCO_PATH=MUJOCO_PATH.replace('\\','/')
    MUJOCO_PLUGIN_PATH=MUJOCO_PLUGIN_PATH.replace('\\','/')

    cmd.run('rm',MUJOCO_PLUGIN_PATH,'-rf')
    cmd.run('rm',MUJOCO_PATH,'-rf')
    cmd.run('mkdir',MUJOCO_PATH)
    cmd.run('mkdir', MUJOCO_PLUGIN_PATH)

    cmd.run('cp' ,'-r', cfg_mujoco_c.install_dir +'/bin/*', MUJOCO_PLUGIN_PATH )
    cmd.run('cp' ,'-r', cfg_mujoco_c.install_dir +'/bin', MUJOCO_PATH )
    cmd.run('cp' ,'-r', cfg_mujoco_c.install_dir +'/lib', MUJOCO_PATH )
    cmd.run('cp' ,'-r', cfg_mujoco_c.install_dir +'/share', MUJOCO_PATH )
    cmd.run('cp' ,'-r', cfg_mujoco_c.install_dir +'/include', MUJOCO_PATH )


def _pip_install_mujoco_py(cmd):
    _create_virtual_env_if_not_exists('.venv',cmd)

    if os.path.exists('./dist'):
        cmd.run('rm', './dist/*','-rf')
    cmd.run('bash', './make_sdist.sh')

    f = os.listdir('./dist')[0]
    f='./dist/'+ f
    #cmd.run('pip', 'install', f,'--verbose','--no-clean')
    cmd.run('pip', 'install', f)


def _bool_to_on_off(b):
    return 'ON' if b  else 'OFF'

def _get_Simulator_Config(curr_dir):
    simulator_bin_dir = _join_path(curr_dir,'..','Style3DSimulatorBin')
    if sys.platform == "win32":
        return _join_path(simulator_bin_dir,'win','lib','cmake','Style3DSimulator')
    else:
        return _join_path(simulator_bin_dir,'linux','lib','cmake','Style3DSimulator')


def _join_path(*paths):
    return os.path.abspath(os.path.join(*paths)).replace('\\','/')

def _cmake_kv(k,v):
    return '-D'+k+'='+v

def _read_me():
    print('make sure the folowing is ready:')
    print('- set environment variable MUJOCO_PATH, e.g some_path')
    print('- set environment variable MUJOCO_PLUGIN_PATH, e.g $MUJOCO_PATH/mujoco_plugin')
    if sys.platform == "win32":
        print('- set environment variable GIT_BASH if you are on Windows, e.g your_git/bin/bash.exe')
    else:
        print('- install libs if you are on Linux:')
        print('  - sudo apt update && sudo apt install libgl1-mesa-dev libxinerama-dev libxcursor-dev libxrandr-dev libxi-dev ninja-build')

def install(configs, cmd):
    for cfg in configs:
        _cmake_install_mujoco_c(cfg.mujoco_c, cmd)
        _pip_install_mujoco_py(cmd)


curr_dir = os.path.dirname(__file__).replace('\\','/')

parser = argparse.ArgumentParser(description=_read_me())
parser.add_argument('--plugin_sim', help='add style3dsim as plugin',action="store_true")
args = parser.parse_args()

cmake_extra_flag = [
    _cmake_kv('MUJOCO_BUILD_STYLE3D',_bool_to_on_off(args.plugin_sim)),
    _cmake_kv('Style3DSimulator_DIR',_get_Simulator_Config(curr_dir)),
    _cmake_kv('CMAKE_POLICY_VERSION_MINIMUM','3.5'),
    _cmake_kv('BUILD_TESTING','OFF'),
    _cmake_kv('DMUJOCO_BUILD_TESTS','OFF'),
]


cmake_source_dir = _join_path(curr_dir,'..')
build_dir = _join_path(curr_dir,'..','temp_build')
install_dir = _join_path(curr_dir,'..','temp_install')

cmake_extra_flag = ' '.join(cmake_extra_flag)

configs = [
    config( cfg_mujoco_c( cmake_source_dir, build_dir ,install_dir, 'Release',cmake_extra_flag) )
]

cmd = cmd_shell()
install(configs, cmd)
