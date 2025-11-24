import shutil
import sys
import subprocess
import threading
import queue
import os
from dataclasses import dataclass

@dataclass
class cfg_mujoco_c:
    src_dir:str
    build_dir:str
    install_dir:str
    build_type:str

@dataclass
class cfg_mujoco_py:
    build_type:str

@dataclass
class config:
    mujoco_c:cfg_mujoco_c
    mujoco_py:cfg_mujoco_py



class cmd_shell:
    def __init__(self ):

        git_bash_key = 'GIT_BASH'
        if git_bash_key in os.environ:
            bash_path = os.environ[git_bash_key]
        else:
            print(f'please set environment variable {git_bash_key}')
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

            #if (something_wrong  and  _check_cmd_begins(stdout_lines)) or _check_output_complete(stdout_lines) :
            if _check_output_complete(stdout_lines):
                break  # No more output for now


        out=''.join(stdout_lines)
        print(out.strip())

        if len(stderr_lines)>0:
            err=''.join(stderr_lines)
            print(err)
            #exit(1)


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

def _echo_cmd(cmd):
    return 'echo $ '+ cmd

def _end_cmd():
    return 'echo '+ end_str

def _return_code_cmd():
    return 'echo $?'

def __copytree(dst, src, symlinks = False, ignore = None):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)

def _copy_dir(dst,src):
    if not os.path.exists(dst):
        os.mkdir(dst)
    __copytree(dst,src)

def _create_virtual_env_if_not_exists(dir,cmd):
    if not os.path.exists(dir):
        cmd.run('python', '-m', 'venv', dir)

    if sys.platform == "win32":
        f = dir + '/Scripts/activate'
        cmd.run('source', f)
    else:
        f = dir + '/bin/activate'
        cmd.run(f)


def _cmake_install_mujoco_c(cfg_mujoco_c, cmd):


    src_flag='-S'+ cfg_mujoco_c.src_dir
    build_dir_flag='-B'+ cfg_mujoco_c.build_dir
    install_flag='-DCMAKE_INSTALL_PREFIX=' + cfg_mujoco_c.install_dir
    build_style3d_flag='-DMUJOCO_BUILD_STYLE3D=OFF'
    version_flag='-DCMAKE_POLICY_VERSION_MINIMUM=3.5'
    BUILD_TESTING='-DBUILD_TESTING=OFF'
    MUJOCO_BUILD_TESTS='-DMUJOCO_BUILD_TESTS=OFF'
    #MUJOCO_TEST_PYTHON_UTIL='-MUJOCO_TEST_PYTHON_UTIL=OFF'

    if not os.path.exists(cfg_mujoco_c.build_dir):
        os.mkdir(cfg_mujoco_c.build_dir)
    cmd.run('cmake', src_flag , build_dir_flag, install_flag, version_flag, build_style3d_flag, BUILD_TESTING, MUJOCO_BUILD_TESTS)

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
    cmd.run('sh', './make_sdist.sh')

    f = os.listdir('./dist')[0]
    f='./dist/'+ f
    #cmd.run('pip', 'install', f,'--verbose','--no-clean')
    cmd.run('pip', 'install', f)


def install(configs, cmd):
    for cfg in configs:
        _cmake_install_mujoco_c(cfg.mujoco_c, cmd)
        _pip_install_mujoco_py(cmd)

configs = [ 
    config( cfg_mujoco_c('..','../temp_build','../temp_install','Release'), cfg_mujoco_py('Release'))
]

cmd =cmd_shell()
install(configs,cmd)