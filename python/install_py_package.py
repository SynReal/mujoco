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

        if sys.platform == "win32":
            bash_path=''
            env_path = os.environ['PATH']
            env_path = env_path.split(';')
            for p in env_path:
                q=p.replace('\\','/')
                if q.endswith('Git/cmd'):
                    bash_path = _join_path(p,'..','bin','bash.exe')

            if bash_path=='':
                print('not found git path!')
                exit(1)

            print(f'found bash: {bash_path}')

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
            shell=True,
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


def _cmake_install_mujoco_c(cfg_mujoco_c, curr_dir, cmd):


    src_flag='-S'+ cfg_mujoco_c.src_dir
    build_dir_flag='-B'+ cfg_mujoco_c.build_dir

    install_dir_flag = _cmake_kv('CMAKE_INSTALL_PREFIX', cfg_mujoco_c.install_dir)

    if not os.path.exists(cfg_mujoco_c.build_dir):
        os.mkdir(cfg_mujoco_c.build_dir)
    cmd.run('cmake', src_flag , build_dir_flag, install_dir_flag, cfg_mujoco_c.cmake_extra_flag)

    cmd.run('rm', cfg_mujoco_c.install_dir + '/*','-rf')
    cmd.run('cmake', '--build' ,cfg_mujoco_c.build_dir, '--target', 'install' , '--config', cfg_mujoco_c.build_type, )


    mujoco_path = cfg_mujoco_c.install_dir
    mujoco_plugin_path = _join_path( mujoco_path,'mujoco_plugin')
    cmd.run('export','MUJOCO_PATH='+mujoco_path)
    cmd.run('export','MUJOCO_PLUGIN_PATH='+mujoco_plugin_path)

    if not os.path.exists(mujoco_plugin_path):
        os.mkdir(mujoco_plugin_path)
    else:
        cmd.run('rm', mujoco_plugin_path + '/*','-rf')

    if sys.platform == "win32":
        cmd.run('cp' ,'-r', cfg_mujoco_c.install_dir +'/bin/*', mujoco_plugin_path )
    else:
        cmd.run('cp' ,'-r', cfg_mujoco_c.install_dir +'/lib/*', mujoco_plugin_path )


def _pip_install_mujoco_py(curr_dir, cmd):
    _create_virtual_env_if_not_exists('.venv',cmd)

    dist_dir=_join_path(curr_dir,'dist')
    if os.path.exists(dist_dir):
        cmd.run('rm', dist_dir+'/*','-rf')
    cmd.run('bash', _join_path(curr_dir,'make_sdist.sh'))

    f=_join_path(dist_dir,'mujoco-*.tar.gz')
    #cmd.run('pip', 'install', f,'--verbose','--no-clean')
    #cmd.run('pip', 'install', f)
    cmd.run('pip', 'wheel','-v','--no-deps', f,'-w',dist_dir)


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
    if sys.platform == "win32":
        pass
    else:
        print('- install libs if you are on Linux:')
        print('  - sudo apt update && sudo apt install cmake gcc-11 g++-11 libgl1-mesa-dev libxinerama-dev libxcursor-dev libxrandr-dev libxi-dev ninja-build libwayland-dev pkg-config libxkbcommon-dev')

def install(configs, curr_dir, cmd):
    for cfg in configs:
        _cmake_install_mujoco_c(cfg.mujoco_c, curr_dir, cmd)
        _pip_install_mujoco_py(curr_dir,cmd)


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
install(configs,curr_dir, cmd)
